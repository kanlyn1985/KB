from __future__ import annotations

import ssl
from dataclasses import dataclass
from http.server import ThreadingHTTPServer
from pathlib import Path


@dataclass(frozen=True)
class TLSConfig:
    certificate_file: Path
    private_key_file: Path
    ca_file: Path | None = None
    require_client_certificate: bool = False
    minimum_tls_version: ssl.TLSVersion = ssl.TLSVersion.TLSv1_2

    def validate(self) -> None:
        for path in (self.certificate_file, self.private_key_file):
            if not path.is_file():
                raise FileNotFoundError(path)
        if self.require_client_certificate and self.ca_file is None:
            raise ValueError("ca_file is required when client certificates are mandatory")
        if self.ca_file is not None and not self.ca_file.is_file():
            raise FileNotFoundError(self.ca_file)


def build_server_ssl_context(config: TLSConfig) -> ssl.SSLContext:
    config.validate()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = config.minimum_tls_version
    context.load_cert_chain(
        certfile=str(config.certificate_file),
        keyfile=str(config.private_key_file),
    )
    context.options |= ssl.OP_NO_COMPRESSION
    if config.ca_file is not None:
        context.load_verify_locations(cafile=str(config.ca_file))
    context.verify_mode = (
        ssl.CERT_REQUIRED if config.require_client_certificate else ssl.CERT_NONE
    )
    return context


def enable_tls(server: ThreadingHTTPServer, config: TLSConfig) -> ThreadingHTTPServer:
    context = build_server_ssl_context(config)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server
