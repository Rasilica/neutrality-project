package com.jinro.apiserver.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Set;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
@RequiredArgsConstructor
public class ApiMethodProtectionFilter extends OncePerRequestFilter {

    private static final String API_PREFIX = "/api/v1/";
    private static final Set<String> ALLOWED_METHODS = Set.of("GET", "OPTIONS");

    private final ApiErrorResponseWriter errorResponseWriter;

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getRequestURI().startsWith(API_PREFIX)
                || ALLOWED_METHODS.contains(request.getMethod());
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain
    ) throws ServletException, IOException {
        response.setHeader(HttpHeaders.ALLOW, "GET, OPTIONS");
        errorResponseWriter.write(
                request,
                response,
                HttpStatus.METHOD_NOT_ALLOWED,
                "공개 기사 API는 GET 요청만 허용합니다."
        );
    }
}
