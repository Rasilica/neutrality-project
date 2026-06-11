package com.jinro.apiserver.exception;

import java.time.ZonedDateTime;

public record ErrorResponseDto(
        int status,
        String error,
        String message,
        String path,
        ZonedDateTime timestamp
) {
}
