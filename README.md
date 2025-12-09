# ActiveMQ Prometheus Metrics Exporter

A Flask-based web server that exports ActiveMQ queue and topic statistics in Prometheus format. This application connects to ActiveMQ via STOMP protocol, retrieves queue/topic metrics using the StatisticsBrokerPlugin, and exposes them for Prometheus scraping.

## Project Structure

```
activemq_gunicorn_metrics/
├── app/
│   ├── main.py              # Flask web server with metrics endpoint
│   ├── queue_discovery.py   # Original standalone discovery script
│   ├── requirements.txt     # Python dependencies
│   ├── Dockerfile          # Docker image for app service
│   └── .env.example        # Environment variables template
├── prometheus/
│   └── prometheus.yml      # Prometheus configuration
├── Dockerfile              # Root-level Dockerfile
└── docker-compose.yml      # Docker Compose orchestration
```

## Features

- **Web Server**: Flask application running on Gunicorn
- **Prometheus Metrics**: Exposes `/metrics` endpoint with ActiveMQ statistics
- **Background Scraper**: Continuously polls ActiveMQ for queue/topic metrics
- **Multi-Broker Support**: Can connect to primary and secondary ActiveMQ brokers
- **SSL Support**: Configurable SSL/TLS connections
- **Health Check**: `/health` endpoint for monitoring
- **Docker Support**: Complete Docker Compose setup with Prometheus

## Metrics Exported

### Queue Metrics
- `activemq_queue_size` - Number of pending messages
- `activemq_queue_enqueue_count` - Total messages enqueued
- `activemq_queue_dequeue_count` - Total messages dequeued
- `activemq_queue_consumer_count` - Active consumers
- `activemq_queue_producer_count` - Active producers

### Topic Metrics
- `activemq_topic_enqueue_count` - Total messages enqueued
- `activemq_topic_dequeue_count` - Total messages dequeued
- `activemq_topic_consumer_count` - Active consumers
- `activemq_topic_producer_count` - Active producers

### Scraper Metrics
- `activemq_scrape_success` - Whether the last scrape was successful (0 or 1)
- `activemq_scrape_duration_seconds` - Duration of the last scrape

## Prerequisites

- Docker and Docker Compose
- ActiveMQ with StatisticsBrokerPlugin enabled
- STOMP protocol enabled on ActiveMQ (port 61614)
- Valid credentials with permissions for `ActiveMQ.Statistics.*` destinations

## Setup

1. **Clone the repository**
   ```bash
   cd /path/to/activemq_gunicorn_metrics
   ```

2. **Configure environment variables**
   ```bash
   cp app/.env.example app/.env
   ```

   Edit `app/.env` with your ActiveMQ details:
   ```env
   ACTIVEMQ_URL=your-activemq-host.com
   ACTIVEMQ_PORT=61614
   ACTIVEMQ_USERNAME=monitor
   ACTIVEMQ_PASSWORD=your-password
   USE_SSL=true
   SCRAPE_INTERVAL=60
   ```

3. **Build and start services**
   ```bash
   docker-compose up -d
   ```

## Usage

### Access Endpoints

- **Metrics Endpoint**: http://localhost:8000/metrics
- **Health Check**: http://localhost:8000/health
- **Home Page**: http://localhost:8000/
- **Prometheus UI**: http://localhost:9090

### View Metrics

```bash
curl http://localhost:8000/metrics
```

### Check Logs

```bash
# View app logs
docker-compose logs -f app

# View Prometheus logs
docker-compose logs -f prometheus
```

### Stop Services

```bash
docker-compose down
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ACTIVEMQ_URL` | `localhost` | Primary ActiveMQ broker hostname |
| `ACTIVEMQ_URL_SECONDARY` | - | Secondary broker (optional, for failover) |
| `ACTIVEMQ_PORT` | `61614` | STOMP port |
| `ACTIVEMQ_USERNAME` | `monitor` | ActiveMQ username |
| `ACTIVEMQ_PASSWORD` | `monitor` | ActiveMQ password |
| `USE_SSL` | `true` | Enable SSL/TLS connection |
| `PORT` | `8000` | Web server port |
| `SCRAPE_INTERVAL` | `60` | Seconds between ActiveMQ scrapes |

### Prometheus Configuration

Edit `prometheus/prometheus.yml` to adjust scraping behavior:

```yaml
scrape_configs:
  - job_name: 'activemq-exporter'
    scrape_interval: 15s
    static_configs:
      - targets: ['app:8000']
```

## Development

### Run Standalone Discovery Script

The original queue discovery script is still available:

```bash
cd app
python queue_discovery.py
```

### Run Flask App Locally

```bash
cd app
pip install -r requirements.txt
python main.py
```

### Build Docker Image Manually

```bash
docker build -t activemq-metrics-exporter .
```

## Troubleshooting

### No Metrics Appearing

1. Check if StatisticsBrokerPlugin is enabled in ActiveMQ
2. Verify user permissions for `ActiveMQ.Statistics.*` destinations
3. Check app logs: `docker-compose logs app`
4. Test connectivity: `curl http://localhost:8000/health`

### Connection Errors

1. Verify ActiveMQ URL and port in `.env`
2. Check SSL configuration matches your ActiveMQ setup
3. Ensure credentials are correct
4. Check network connectivity to ActiveMQ broker

### Prometheus Not Scraping

1. Verify Prometheus is running: `docker-compose ps`
2. Check Prometheus targets: http://localhost:9090/targets
3. Ensure app service is healthy: `docker-compose ps app`
4. Verify network connectivity between containers

## License

MIT

## Contributing

Contributions are welcome! Please submit pull requests or open issues for bugs and feature requests.
