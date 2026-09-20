# DevDuel judge runner — Java
#
# A JDK, not a JRE: submissions are compiled inside the container at run time.
# Pinned, non-root, no application code — same as every other runner.
FROM eclipse-temurin:21.0.5_11-jdk-jammy

RUN groupadd --gid 10001 runner \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin runner \
    && mkdir -p /box \
    && chown runner:runner /box

# The JVM writes its own scratch files; point them at the tmpfs rather than the
# read-only root filesystem, which it would otherwise fail on.
ENV HOME=/tmp \
    JAVA_TOOL_OPTIONS="-Djava.io.tmpdir=/tmp -XX:-UsePerfData"

USER 10001:10001
WORKDIR /box

CMD ["sh", "-c", "echo devduel java runner ready"]
