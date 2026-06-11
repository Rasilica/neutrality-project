package com.jinro.apiserver.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.time.Clock;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicReference;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 30)
@RequiredArgsConstructor
public class ApiRateLimitFilter extends OncePerRequestFilter {

    private static final String API_PREFIX = "/api/v1/";

    private final RateLimitProperties rateLimitProperties;
    private final ApiErrorResponseWriter errorResponseWriter;
    private final Clock clock = Clock.systemUTC();
    private final ConcurrentMap<String, WindowState> windows = new ConcurrentHashMap<>();

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !rateLimitProperties.isEnabled()
                || !request.getRequestURI().startsWith(API_PREFIX)
                || "OPTIONS".equalsIgnoreCase(request.getMethod());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        long nowMillis = clock.millis();
        long windowMillis = rateLimitProperties.getWindowSeconds() * 1000L;
        String clientKey = clientKey(request);
        AtomicReference<WindowState> updatedState = new AtomicReference<>();

        windows.compute(clientKey, (key, current) -> {
            WindowState next = nextState(current, nowMillis, windowMillis);
            updatedState.set(next);
            return next;
        });

        cleanupExpiredWindows(nowMillis, windowMillis);

        WindowState state = updatedState.get();
        int limit = rateLimitProperties.getLimit();
        int remaining = Math.max(limit - state.requestCount(), 0);

        response.setHeader("X-RateLimit-Limit", String.valueOf(limit));
        response.setHeader("X-RateLimit-Remaining", String.valueOf(remaining));

        if (state.requestCount() > limit) {
            response.setHeader("Retry-After", String.valueOf(retryAfterSeconds(state, nowMillis, windowMillis)));
            errorResponseWriter.write(
                    request,
                    response,
                    HttpStatus.TOO_MANY_REQUESTS,
                    "요청이 너무 많습니다. 잠시 후 다시 시도하세요."
            );
            return;
        }

        filterChain.doFilter(request, response);
    }

    private WindowState nextState(WindowState current, long nowMillis, long windowMillis) {
        if (current == null || nowMillis - current.startedAtMillis() >= windowMillis) {
            return new WindowState(nowMillis, 1);
        }
        return new WindowState(current.startedAtMillis(), current.requestCount() + 1);
    }

    private void cleanupExpiredWindows(long nowMillis, long windowMillis) {
        if (windows.size() < rateLimitProperties.getCleanupThreshold()) {
            return;
        }
        windows.entrySet().removeIf(entry -> nowMillis - entry.getValue().startedAtMillis() >= windowMillis * 2);
    }

    private String clientKey(HttpServletRequest request) {
        String remoteAddr = request.getRemoteAddr();
        if (remoteAddr == null || remoteAddr.isBlank()) {
            return "unknown";
        }
        return remoteAddr;
    }

    private long retryAfterSeconds(WindowState state, long nowMillis, long windowMillis) {
        long elapsedMillis = nowMillis - state.startedAtMillis();
        long remainingMillis = Math.max(windowMillis - elapsedMillis, 0);
        return Math.max((long) Math.ceil(remainingMillis / 1000.0), 1);
    }

    private record WindowState(long startedAtMillis, int requestCount) {
    }
}
