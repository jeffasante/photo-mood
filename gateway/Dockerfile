FROM node:18-alpine

WORKDIR /usr/src/app

# Copy package.json first
COPY package.json ./

# Install dependencies
RUN npm install --only=production

# Copy the gateway source code
COPY index.js ./

# Copy the web frontend files into the container
COPY web ./web

EXPOSE 3000
CMD [ "node", "index.js" ]