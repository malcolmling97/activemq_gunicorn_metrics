import os
import time
import ssl
import uuid
import stomp
import threading
from flask import Flask, Response
from prometheus_client import Counter, Gauge, generate_latest, REGISTRY
from dotenv import load_dotenv
import xml.etree.ElementTree as ET

load_dotenv()

ACTIVEMQ_URL = os.getenv('ACTIVEMQ_URL', 'localhost')
ACTIVEMQ_URL_SECONDARY = os.getenv('ACTIVEMQ_URL_SECONDARY', '')
ACTIVEMQ_PORT = int(os.getenv('ACTIVEMQ_PORT', 61614))
USER = os.getenv('ACTIVEMQ_USERNAME', 'monitor')
PASSWORD = os.getenv('ACTIVEMQ_PASSWORD', 'monitor')
USE_SSL = os.getenv('USE_SSL', 'true').lower() == 'true'
SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '60'))

BROKER_HOSTS = [(ACTIVEMQ_URL, ACTIVEMQ_PORT)]
if ACTIVEMQ_URL_SECONDARY:
    BROKER_HOSTS.append((ACTIVEMQ_URL_SECONDARY, ACTIVEMQ_PORT))

app = Flask(__name__)

# No global state needed - Prometheus registry handles everything

# Prometheus metrics
activemq_queue_size = Gauge('activemq_queue_size', 'Queue size (pending messages)', ['queue', 'broker'])
activemq_queue_enqueue_count = Counter('activemq_queue_enqueue_count', 'Total enqueued messages', ['queue', 'broker'])
activemq_queue_dequeue_count = Counter('activemq_queue_dequeue_count', 'Total dequeued messages', ['queue', 'broker'])
activemq_queue_consumer_count = Gauge('activemq_queue_consumer_count', 'Active consumers', ['queue', 'broker'])
activemq_queue_producer_count = Gauge('activemq_queue_producer_count', 'Active producers', ['queue', 'broker'])

activemq_topic_enqueue_count = Counter('activemq_topic_enqueue_count', 'Total enqueued messages', ['topic', 'broker'])
activemq_topic_dequeue_count = Counter('activemq_topic_dequeue_count', 'Total dequeued messages', ['topic', 'broker'])
activemq_topic_consumer_count = Gauge('activemq_topic_consumer_count', 'Active consumers', ['topic', 'broker'])
activemq_topic_producer_count = Gauge('activemq_topic_producer_count', 'Active producers', ['topic', 'broker'])

activemq_scrape_success = Gauge('activemq_scrape_success', 'Whether the last scrape was successful')
activemq_scrape_duration = Gauge('activemq_scrape_duration_seconds', 'Duration of the last scrape')

class StatisticsListener(stomp.ConnectionListener):
    def __init__(self):
        self.queues = {}
        self.topics = {}
        self.broker_name = None
        self.connected = False
        self.response_received = False
        self.any_response_received = False

    def on_error(self, frame):
        print(f"[ERROR] {frame.body}")

    def on_connected(self, frame):
        print("[INFO] Connected to broker")
        self.connected = True

    def on_disconnected(self):
        print("[INFO] Disconnected from broker")
        self.connected = False

    def on_message(self, frame):
        self.response_received = True
        self.any_response_received = True

        try:
            if frame.body and '<map>' in frame.body:
                root = ET.fromstring(frame.body)
                stats = {}
                destination_name = None

                for entry in root.findall('.//entry'):
                    children = list(entry)
                    if len(children) >= 2:
                        key_elem = children[0]
                        value_elem = children[1]

                        if key_elem.tag == 'string' and key_elem.text:
                            key_name = key_elem.text
                            value = value_elem.text if value_elem.text is not None else ''
                            stats[key_name] = value

                            if key_name == 'destinationName':
                                destination_name = value
                            elif key_name == 'brokerName':
                                self.broker_name = value

                if destination_name:
                    if destination_name.startswith('queue://'):
                        queue_name = destination_name.replace('queue://', '')
                        self.queues[queue_name] = stats
                        print(f"[INFO] Found queue: {queue_name}")
                    elif destination_name.startswith('topic://'):
                        topic_name = destination_name.replace('topic://', '')
                        self.topics[topic_name] = stats
                        print(f"[INFO] Found topic: {topic_name}")

        except Exception as e:
            print(f"[WARN] Error processing statistics response: {e}")

def discover_destinations():
    broker_list = ', '.join([f"{h}:{p}" for h, p in BROKER_HOSTS])
    print(f"[INFO] Starting destination discovery (SSL: {USE_SSL})")
    print(f"[INFO] Broker(s): {broker_list}")

    listener = StatisticsListener()
    conn = stomp.Connection(BROKER_HOSTS, heartbeats=(10000, 10000))

    if USE_SSL:
        conn.set_ssl(for_hosts=BROKER_HOSTS, ssl_version=ssl.PROTOCOL_TLS)

    conn.set_listener('statistics', listener)

    try:
        conn.connect(USER, PASSWORD, wait=True, headers={'heart-beat': '10000,10000'})

        reply_queue = f'/temp-queue/stats.reply.{uuid.uuid4().hex[:8]}'
        conn.subscribe(destination=reply_queue, id=1, ack='auto')

        statistics_destinations = [
            'ActiveMQ.Statistics.Destination.>',
            'ActiveMQ.Statistics.Broker',
        ]

        for statistics_destination in statistics_destinations:
            print(f"[INFO] Sending statistics request to: {statistics_destination}")
            listener.response_received = False

            try:
                conn.send(
                    body='',
                    destination=statistics_destination,
                    headers={'reply-to': reply_queue}
                )
            except Exception as send_error:
                print(f"[ERROR] Failed to send statistics request: {send_error}")
                continue

            timeout = 15
            last_response_time = time.time()

            for i in range(timeout, 0, -1):
                if listener.response_received:
                    last_response_time = time.time()
                    listener.response_received = False

                if listener.queues or listener.topics:
                    time_since_last = time.time() - last_response_time
                    if time_since_last > 3:
                        break

                time.sleep(1)

            if listener.queues or listener.topics:
                print(f"[SUCCESS] Found {len(listener.queues)} queues and {len(listener.topics)} topics")
                break

        if listener.broker_name:
            print(f"[INFO] Broker name: {listener.broker_name}")

        return listener

    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return None
    finally:
        if conn.is_connected():
            conn.disconnect()

def update_metrics():
    start_time = time.time()
    try:
        listener = discover_destinations()

        if listener:
            broker_name = listener.broker_name or 'unknown'

            # Update queue metrics
            for queue_name, stats in listener.queues.items():
                if not queue_name.startswith('ActiveMQ.'):
                    try:
                        size = int(stats.get('size', 0))
                        activemq_queue_size.labels(queue=queue_name, broker=broker_name).set(size)

                        enqueue_count = int(stats.get('enqueueCount', 0))
                        activemq_queue_enqueue_count.labels(queue=queue_name, broker=broker_name)._value._value = enqueue_count

                        dequeue_count = int(stats.get('dequeueCount', 0))
                        activemq_queue_dequeue_count.labels(queue=queue_name, broker=broker_name)._value._value = dequeue_count

                        consumer_count = int(stats.get('consumerCount', 0))
                        activemq_queue_consumer_count.labels(queue=queue_name, broker=broker_name).set(consumer_count)

                        producer_count = int(stats.get('producerCount', 0))
                        activemq_queue_producer_count.labels(queue=queue_name, broker=broker_name).set(producer_count)
                    except ValueError as e:
                        print(f"[WARN] Failed to parse metric for queue {queue_name}: {e}")

            # Update topic metrics
            for topic_name, stats in listener.topics.items():
                if not topic_name.startswith('ActiveMQ.'):
                    try:
                        enqueue_count = int(stats.get('enqueueCount', 0))
                        activemq_topic_enqueue_count.labels(topic=topic_name, broker=broker_name)._value._value = enqueue_count

                        dequeue_count = int(stats.get('dequeueCount', 0))
                        activemq_topic_dequeue_count.labels(topic=topic_name, broker=broker_name)._value._value = dequeue_count

                        consumer_count = int(stats.get('consumerCount', 0))
                        activemq_topic_consumer_count.labels(topic=topic_name, broker=broker_name).set(consumer_count)

                        producer_count = int(stats.get('producerCount', 0))
                        activemq_topic_producer_count.labels(topic=topic_name, broker=broker_name).set(producer_count)
                    except ValueError as e:
                        print(f"[WARN] Failed to parse metric for topic {topic_name}: {e}")

            activemq_scrape_success.set(1)
        else:
            activemq_scrape_success.set(0)

    except Exception as e:
        print(f"[ERROR] Failed to update metrics: {e}")
        activemq_scrape_success.set(0)

    duration = time.time() - start_time
    activemq_scrape_duration.set(duration)
    print(f"[INFO] Metrics updated in {duration:.2f}s")

def background_scraper():
    print(f"[INFO] Starting background scraper (interval: {SCRAPE_INTERVAL}s)", flush=True)
    # Run initial scrape immediately
    update_metrics()
    # Then continue with periodic scraping
    while True:
        time.sleep(SCRAPE_INTERVAL)
        update_metrics()

# Start background thread when module is loaded (works with Gunicorn)
scraper_thread = threading.Thread(target=background_scraper, daemon=True)
scraper_thread.start()

@app.route('/')
def index():
    return 'ActiveMQ Metrics Exporter - visit /metrics for Prometheus metrics'

@app.route('/metrics')
def metrics():
    return Response(generate_latest(REGISTRY), mimetype='text/plain')


@app.route('/health')
def health():
    return {'status': 'ok'}, 200

if __name__ == '__main__':
    # Background scraper already started at module load (line 235)
    # Start Flask server
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
