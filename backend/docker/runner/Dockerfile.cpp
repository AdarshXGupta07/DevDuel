# DevDuel judge runner — C++
#
# Same rules as the other runners: pinned version, non-root, contains no application
# code. gcc's image is large (~1.3GB); that is the cost of a compiler and it is paid
# once at build time, not per submission.
FROM gcc:13.3.0

RUN groupadd --gid 10001 runner \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin runner \
    && mkdir -p /box \
    && chown runner:runner /box

ENV HOME=/tmp

USER 10001:10001
WORKDIR /box

CMD ["sh", "-c", "echo devduel cpp runner ready"]
