FROM node:18-alpine

WORKDIR /app

COPY gateway/package*.json ./
RUN npm install

COPY gateway/ ./

EXPOSE 3000

CMD ["npm", "start"]