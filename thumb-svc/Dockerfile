# Multi-stage build for smaller image
FROM golang:1.21-alpine AS builder

WORKDIR /app

# Install dependencies
COPY go.mod go.sum ./
RUN go mod download

# Build the application
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o thumb-svc .

# Final stage
FROM alpine:latest

RUN apk --no-cache add ca-certificates
WORKDIR /root/

# Copy binary from builder stage
COPY --from=builder /app/thumb-svc .

EXPOSE 5002
CMD ["./thumb-svc"]