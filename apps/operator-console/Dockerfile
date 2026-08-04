FROM node:22.13.1-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/operator-console ./apps/operator-console
RUN npm --prefix apps/operator-console run build

FROM node:22.13.1-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=8080
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/apps/operator-console/dist ./dist
USER app
EXPOSE 8080
CMD ["node", "dist/src/server.js"]
