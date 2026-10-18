FROM oven/bun:1.3.0@sha256:00cccad6e9c66bbacc250851f689168606aaea551ac473e908bbcf00a5645025 AS build
USER root
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /source
RUN git init . && git remote add origin https://github.com/przbadu/hermes-ui.git && git fetch --depth 1 origin 1af684e2d6ce05e6d1da82d67bc671e15d2d2d96 && git checkout --detach FETCH_HEAD
COPY patch_profile.py /patch_profile.py
WORKDIR /source/app
RUN python3 /patch_profile.py && bun install --frozen-lockfile --ignore-scripts
RUN bun run build
FROM nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236
COPY --from=build /source/app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
USER 101:101
EXPOSE 8080

