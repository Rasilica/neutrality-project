package com.jinro.apiserver.logging;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class RequestLoggingFilter extends OncePerRequestFilter {

    private static final Logger logger = LoggerFactory.getLogger(RequestLoggingFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        long startedAt = System.currentTimeMillis();
        String requestTarget = buildRequestTarget(request);

        try {
            filterChain.doFilter(request, response);
        } catch (ServletException | IOException | RuntimeException exception) {
            long elapsedMillis = System.currentTimeMillis() - startedAt;
            logger.error(
                    "HTTP {} {} failed after {} ms",
                    request.getMethod(),
                    requestTarget,
                    elapsedMillis,
                    exception
            );
            throw exception;
        } finally {
            long elapsedMillis = System.currentTimeMillis() - startedAt;
            logger.info(
                    "HTTP {} {} -> {} ({} ms)",
                    request.getMethod(),
                    requestTarget,
                    response.getStatus(),
                    elapsedMillis
            );
        }
    }

    private String buildRequestTarget(HttpServletRequest request) {
        String queryString = request.getQueryString();
        if (queryString == null || queryString.isBlank()) {
            return request.getRequestURI();
        }
        return request.getRequestURI() + "?" + queryString;
    }
}
