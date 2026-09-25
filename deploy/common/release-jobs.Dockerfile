FROM node:22.13.1-alpine
WORKDIR /app
COPY package.json package-lock.json tsconfig.json vitest.config.ts ./
COPY gateway ./gateway
COPY packages ./packages
COPY automations ./automations
COPY scripts ./scripts
COPY ops ./ops
COPY supabase ./supabase
# The ops scripts are bash (mapfile) and call curl and shasum.
RUN apk add --no-cache bash curl perl-utils \
  && npm ci --ignore-scripts --no-audit --no-fund \
  && chmod 0755 ops/migration-preflight.sh ops/publish-certified-packages.sh ops/run-operations-scheduler.sh ops/reconcile-disposable-eval-resources.sh \
  && addgroup -S linkautowork && adduser -S -G linkautowork linkautowork \
  && chown -R linkautowork:linkautowork /app
USER linkautowork
