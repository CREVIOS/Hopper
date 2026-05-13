FROM node:22-slim AS builder

# Pin pnpm 9 to match CI and avoid pnpm 10+ "ignored build scripts" breaking esbuild in Docker.
RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM node:22-slim

RUN corepack enable && corepack prepare pnpm@9 --activate

WORKDIR /app
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json .
COPY --from=builder /app/node_modules ./node_modules

ENV NODE_ENV=production
EXPOSE 3000
CMD ["node", "build"]
