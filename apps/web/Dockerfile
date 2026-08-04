FROM node:22.13.1-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/web ./apps/web
RUN npm --prefix apps/web run build

FROM node:22.13.1-alpine
WORKDIR /app
ENV NODE_ENV=production PORT=8080
RUN addgroup -S app && adduser -S app -G app
COPY --from=build --chown=app:app /app/apps/web/dist ./dist
USER app
EXPOSE 8080
CMD ["node", "dist/src/server.js"]
