# Use the official Node.js 24 slim image as the base image
FROM node:24-slim as base


# Set the working directory inside the container
WORKDIR /app

# posthog-cli loads CA certs from the system store, which node:slim doesn't ship
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*


# Build-time public config. Defaults are the hosted service's values so an
# argument-less build is unchanged; a self-hosted build passes its own with
# --build-arg (NEXT_PUBLIC_* is inlined by `next build`, so it must be here).
ARG NEXT_PUBLIC_API_URL=https://api.openpaper.ai
ARG NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_live_51O33aTCUG3OIDR6rhzcP0aDTftZyC07Iyf59NG8dAjPCLcmKyv0ADqSfO9CUYz5ugF7GI91JcyM6rIwp56Ehp41V00MYxGF8d7
ARG NEXT_PUBLIC_POSTHOG_KEY=phc_i84JqfidoQncsSmusoeZF9oshYHV2SebGZkKMVtF8AG
ARG NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=$NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY
ENV NEXT_PUBLIC_POSTHOG_HOST=$NEXT_PUBLIC_POSTHOG_HOST


# Copy package.json and yarn.lock to the working directory
# This is done separately to leverage Docker cache.
# If these files haven't changed, Docker will use the cached layer for yarn install.
COPY package.json yarn.lock ./


# Install dependencies using yarn and posthog-cli for source map uploads
# Only run this if package.json or yarn.lock changed
# Using --frozen-lockfile for reproducible and potentially faster installs
RUN yarn install --frozen-lockfile && \
    yarn global add @posthog/cli

# Add yarn global bin to PATH
ENV PATH="/root/.yarn/bin:$PATH"


# Copy the rest of the application code to the working directory
# This layer will only be rebuilt if the application code changes.
# Ensure .dockerignore is properly configured to exclude unnecessary files.
COPY . .


# Build the Next.js application
# This will only run if the code (above) or dependencies (further above) changed.
RUN yarn build

# Upload source maps to PostHog, then delete them from the build. Skipped
# when the build has no PostHog secrets (self-hosted builds).
RUN --mount=type=secret,id=POSTHOG_ENV_ID \
    --mount=type=secret,id=POSTHOG_CLI_TOKEN \
    if [ -s /run/secrets/POSTHOG_ENV_ID ] && [ -s /run/secrets/POSTHOG_CLI_TOKEN ]; then \
      export POSTHOG_CLI_ENV_ID="$(cat /run/secrets/POSTHOG_ENV_ID)" && \
      export POSTHOG_CLI_TOKEN="$(cat /run/secrets/POSTHOG_CLI_TOKEN)" && \
      posthog-cli sourcemap inject --directory .next && \
      posthog-cli sourcemap upload --directory .next; \
    else \
      echo "No PostHog secrets: skipping source map upload"; \
    fi && \
    find .next -name '*.map' -delete


# Use the official Node.js 24 slim image for running the app
FROM node:24-slim as production


# Set the working directory
WORKDIR /app


# Set production environment variables
ENV NODE_ENV=production
# ARGs do not cross stages; redeclare so the runtime sees the same values
# the bundle was built with.
ARG NEXT_PUBLIC_API_URL=https://api.openpaper.ai
ARG NEXT_PUBLIC_POSTHOG_KEY=phc_i84JqfidoQncsSmusoeZF9oshYHV2SebGZkKMVtF8AG
ARG NEXT_PUBLIC_POSTHOG_HOST=https://us.i.posthog.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY
ENV NEXT_PUBLIC_POSTHOG_HOST=$NEXT_PUBLIC_POSTHOG_HOST


# Copy the built application from the base image
COPY --from=base /app/.next ./.next
COPY --from=base /app/public ./public
COPY --from=base /app/package.json ./
COPY --from=base /app/yarn.lock ./


# Install only the production dependencies
# This ensures a smaller final image by not including devDependencies
RUN yarn install --production --frozen-lockfile


# Expose port 3000 to the outside world
EXPOSE 3000


# Define the command to start the Next.js application
CMD ["yarn", "start"]
