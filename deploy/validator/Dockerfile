ARG TERRAFORM_VERSION
ARG AWS_CLI_VERSION
ARG PYTHON_IMAGE=python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
FROM hashicorp/terraform:${TERRAFORM_VERSION} AS terraform
FROM public.ecr.aws/aws-cli/aws-cli:${AWS_CLI_VERSION} AS awscli
FROM ${PYTHON_IMAGE} AS provider
ARG AWS_PROVIDER_VERSION
COPY --from=terraform /bin/terraform /usr/local/bin/terraform
WORKDIR /build
RUN printf 'terraform {\n required_providers {\n aws = {\n source = "hashicorp/aws"\n version = "= %s"\n }\n }\n}\n' "$AWS_PROVIDER_VERSION" > main.tf \
 && terraform init -backend=false -input=false \
 && mkdir /providers && cp -a .terraform/providers/. /providers/
FROM ${PYTHON_IMAGE}
ARG CFN_LINT_VERSION
RUN pip install --no-cache-dir cfn-lint==${CFN_LINT_VERSION}
COPY --from=terraform /bin/terraform /usr/local/bin/terraform
COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
RUN ln -s /usr/local/aws-cli/v2/current/bin/aws /usr/local/bin/aws
COPY --from=provider /providers /providers
COPY server.py toolchain.json /app/
ENV AWS_EC2_METADATA_DISABLED=true AWS_DEFAULT_REGION=us-east-1 AWS_PAGER="" TF_IN_AUTOMATION=1 CHECKPOINT_DISABLE=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp
USER 10001:10001
WORKDIR /app
EXPOSE 9130
ENTRYPOINT ["python", "/app/server.py"]
