FROM ghcr.io/berriai/litellm:main-stable

COPY config.yaml /app/config.yaml

CMD ["--config", "/app/config.yaml", "--port", "4000", "--host", "0.0.0.0"]
