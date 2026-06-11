package com.jinro.apiserver.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
@RequiredArgsConstructor
public class ApiSecurityHeadersFilter extends OncePerRequestFilter {

    private final ApiSecurityProperties apiSecurityProperties;

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        applyHeaderIfAbsent(response, "X-Content-Type-Options", "nosniff");
        applyHeaderIfAbsent(response, "X-Frame-Options", "DENY");
        applyHeaderIfAbsent(response, "Referrer-Policy", "no-referrer");
        applyHeaderIfAbsent(response, "Permissions-Policy", "geolocation=(), microphone=(), camera=()");
        applyHeaderIfAbsent(response, "Content-Security-Policy", apiSecurityProperties.getContentSecurityPolicy());

        if (apiSecurityProperties.isHstsEnabled() && isHttpsRequest(request)) {
            applyHeaderIfAbsent(
                    response,
                    "Strict-Transport-Security",
                    "max-age=" + apiSecurityProperties.getHstsMaxAgeSeconds() + "; includeSubDomains"
            );
        }

        filterChain.doFilter(request, response);
    }

    private void applyHeaderIfAbsent(HttpServletResponse response, String name, String value) {
        if (!response.containsHeader(name)) {
            response.setHeader(name, value);
        }
    }

    private boolean isHttpsRequest(HttpServletRequest request) {
        return request.isSecure() || "https".equalsIgnoreCase(request.getHeader("X-Forwarded-Proto"));
    }
}
