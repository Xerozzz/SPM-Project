# Development image: it runs the Vite dev server with hot module replacement.
# A production build would be a multi-stage `vite build` into nginx; we do not need one
# for a local stack, and an image we can all explain is worth more than one we cannot.
FROM node:20-slim

WORKDIR /app

# Dependencies first so this layer is cached until package.json changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
