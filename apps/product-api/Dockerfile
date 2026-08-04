FROM node:22.13.1-alpine AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

FROM dependencies AS build
COPY apps/product-api ./apps/product-api
RUN npx tsc -p apps/product-api/tsconfig.production.json --outDir /tmp/product-api-build

FROM node:22.13.1-alpine
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S linkautowork && adduser -S -G linkautowork linkautowork
COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=build /tmp/product-api-build ./dist
USER linkautowork
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD node -e "fetch('http://127.0.0.1:8080/healthz').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "dist/server.js"]
