package com.jinro.apiserver.security;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.time.ZonedDateTime;

@Component
public class ApiErrorResponseWriter {

    public void write(
            HttpServletRequest request,
            HttpServletResponse response,
            HttpStatus status,
            String message
    ) throws IOException {
        if (response.isCommitted()) {
            return;
        }

        response.setStatus(status.value());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding("UTF-8");
        response.getWriter().write(toJson(request, status, message));
    }

    private String toJson(HttpServletRequest request, HttpStatus status, String message) {
        return "{"
                + "\"status\":" + status.value() + ","
                + "\"error\":\"" + escapeJson(status.getReasonPhrase()) + "\","
                + "\"message\":\"" + escapeJson(message) + "\","
                + "\"path\":\"" + escapeJson(request.getRequestURI()) + "\","
                + "\"timestamp\":\"" + ZonedDateTime.now() + "\""
                + "}";
    }

    private String escapeJson(String value) {
        if (value == null) {
            return "";
        }
        return value
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
