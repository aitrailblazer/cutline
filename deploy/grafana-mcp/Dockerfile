# Official Grafana MCP image, pinned to the verified 2026-07-31 OCI index.
FROM docker.io/grafana/mcp-grafana@sha256:5efeafd01cd7e1aea9c4b0f03305951f2944db8f43e5ae290cce9578c977f241

ENTRYPOINT ["/app/mcp-grafana"]
CMD ["--transport", "streamable-http", "--address", "0.0.0.0:8080", "--allowed-hosts=*", "--disable-write", "--metrics"]
