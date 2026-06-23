# Stage 1: Build the React application using Vite
FROM node:20-alpine AS build
WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy application source code (including .env.production)
COPY . .

# Build the application
RUN npm run build

# Stage 2: Serve the app using Nginx
FROM nginx:alpine

# Copy built static files from the build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy the Nginx configuration template
# Nginx 1.19+ automatically processes templates in this directory and outputs to /etc/nginx/conf.d/
COPY default.conf.template /etc/nginx/templates/default.conf.template

# Cloud Run defaults to expecting port 8080
EXPOSE 8080

# Run Nginx
CMD ["nginx", "-g", "daemon off;"]
