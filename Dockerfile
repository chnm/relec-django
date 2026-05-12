FROM rust AS volta-build
WORKDIR /src
RUN git clone https://github.com/volta-cli/volta.git /src
RUN cargo build
RUN ls /src/target/debug

FROM python:slim-trixie
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/venv

# Set working directory
WORKDIR /app

# Copy project
COPY . /app/

RUN uv lock

# Copy over Volta binaries
RUN mkdir -p /root/.volta/bin
COPY --from=volta-build /src/target/debug/volta /root/.volta/bin
COPY --from=volta-build /src/target/debug/volta-migrate /root/.volta/bin
COPY --from=volta-build /src/target/debug/volta-shim /root/.volta/bin

# shell stuff for volta
SHELL ["/bin/bash", "-c"]
ENV BASH_ENV ~/.bashrc
ENV VOLTA_HOME /root/.volta
ENV PATH $VOLTA_HOME/bin:$PATH

RUN ln -s /root/.volta/bin/volta-shim /root/.volta/bin/node 
RUN ln -s /root/.volta/bin/volta-shim /root/.volta/bin/npm 
RUN ln -s /root/.volta/bin/volta-shim /root/.volta/bin/npx
RUN ln -s /root/.volta/bin/volta-shim /root/.volta/bin/pnpm 
RUN ln -s /root/.volta/bin/volta-shim /root/.volta/bin/yarn

# triggers node installation
RUN node -v && npm -v
RUN npm install

# generate front end assets
RUN uv run manage.py tailwind install
RUN uv run manage.py tailwind build
RUN uv run manage.py collectstatic --no-input

# clean up
RUN rm -rf /root/.volta
RUN rm -rf /app/node_modules

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/', timeout=4).status == 200 else 1)"

CMD uv run manage.py runserver 0.0.0.0:8000
