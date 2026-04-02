FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json tsconfig.json vitest.config.ts ./
COPY gateway ./gateway
RUN npm install --no-audit --no-fund

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app /app
RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/dist /app/dist
COPY --from=deps /app/node_modules /app/node_modules
COPY --from=deps /app/package.json /app/package.json
RUN addgroup -S app && adduser -S -G app app && chown -R app:app /app
USER app
EXPOSE 8080
CMD ["node", "dist/gateway/src/server.js"]
