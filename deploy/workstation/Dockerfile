# RemediGenius Community Edition (RemediGenius-CE) desk container for the Docker workstation path.
# It is the only container with AWS credentials (temporary, refreshed by tools/workstation.py).
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
ARG TERRAFORM_VERSION=1.12.2
ARG TERRAFORM_SHA256=1eaed12ca41fcfe094da3d76a7e9aa0639ad3409c43be0103ee9f5a1ff4b7437
RUN pip install --no-cache-dir boto3==1.42.89 PyYAML==6.0.2 \
 && python -c "import hashlib,io,os,urllib.request,zipfile; v=os.environ['TERRAFORM_VERSION']; d=urllib.request.urlopen(f'https://releases.hashicorp.com/terraform/{v}/terraform_{v}_linux_amd64.zip',timeout=120).read(); assert hashlib.sha256(d).hexdigest()==os.environ['TERRAFORM_SHA256'],'terraform checksum mismatch'; open('/usr/local/bin/terraform','wb').write(zipfile.ZipFile(io.BytesIO(d)).read('terraform')); os.chmod('/usr/local/bin/terraform',0o755)" \
 && groupadd --gid 10000 remedigenius && useradd --uid 10000 --gid 10000 --no-create-home --shell /usr/sbin/nologin remedigenius
COPY rgtriage /opt/rgtriage/rgtriage
ENV PYTHONPATH=/opt/rgtriage RGTRIAGE_HOME=/data/rgtriage HOME=/data/rgtriage/.home TF_PLUGIN_CACHE_DIR=/data/rgtriage/.home/plugins \
    AWS_SHARED_CREDENTIALS_FILE=/creds/credentials AWS_CONFIG_FILE=/creds/config PYTHONIOENCODING=utf-8
USER 10000:10000
ENTRYPOINT ["python", "-m", "rgtriage"]
