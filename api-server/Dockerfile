FROM eclipse-temurin:17-jdk-jammy AS build

WORKDIR /workspace
COPY gradle gradle
COPY gradlew build.gradle settings.gradle ./
RUN chmod +x gradlew
COPY src src
RUN ./gradlew --no-daemon bootJar

FROM eclipse-temurin:17-jre-jammy

WORKDIR /app
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/logs \
    && chown appuser:appuser /app/logs
COPY --from=build --chown=appuser:appuser /workspace/build/libs/demo-0.0.1-SNAPSHOT.jar app.jar

USER appuser
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
