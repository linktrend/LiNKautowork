FROM node:22.13.1-alpine AS deps
WORKDIR /app
# Generic gateway image: lockfile-pinned npm ci only. AW-03 owns lock mutations.
# Provider/runtime-dispatch source is compiled in later packets; this image stays
# the existing gateway contract, not a second service.
COPY package.json package-lock.json tsconfig.json ./
COPY gateway ./gateway
RUN npm ci --ignore-scripts --no-audit --no-fund

FROM node:22.13.1-alpine AS build
WORKDIR /app
COPY --from=deps /app /app
RUN npm run build

FROM node:22.13.1-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist /app/dist
COPY --from=deps /app/node_modules /app/node_modules
COPY --from=deps /app/package.json /app/package.json
COPY --from=deps /app/package-lock.json /app/package-lock.json
RUN addgroup -S app && adduser -S -G app app && chown -R app:app /app
USER app
EXPOSE 8080
CMD ["node", "dist/gateway/src/server.js"]
