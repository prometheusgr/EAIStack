FROM node:20-alpine

WORKDIR /app

COPY package*.json .
RUN npm install

COPY . .

# Make entrypoint executable
RUN chmod +x docker-entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
