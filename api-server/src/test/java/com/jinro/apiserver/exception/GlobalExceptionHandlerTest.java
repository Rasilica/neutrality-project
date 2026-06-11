package com.jinro.apiserver.exception;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;

import static org.assertj.core.api.Assertions.assertThat;

class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Test
    void badRequestReturnsStandardErrorResponse() {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/articles/not-a-number");

        ResponseEntity<ErrorResponseDto> response = handler.handleBadRequest(
                new IllegalArgumentException("잘못된 요청입니다."),
                request
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().status()).isEqualTo(400);
        assertThat(response.getBody().error()).isEqualTo("Bad Request");
        assertThat(response.getBody().message()).isEqualTo("잘못된 요청입니다.");
        assertThat(response.getBody().path()).isEqualTo("/api/v1/articles/not-a-number");
    }

    @Test
    void notFoundReturnsStandardErrorResponse() {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/v1/articles/999999");

        ResponseEntity<ErrorResponseDto> response = handler.handleNotFound(
                new ResourceNotFoundException("존재하지 않는 기사입니다. id=999999"),
                request
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().status()).isEqualTo(404);
        assertThat(response.getBody().error()).isEqualTo("Not Found");
        assertThat(response.getBody().message()).isEqualTo("존재하지 않는 기사입니다. id=999999");
        assertThat(response.getBody().path()).isEqualTo("/api/v1/articles/999999");
    }

    @Test
    void internalServerErrorDoesNotExposeExceptionMessage() {
        MockHttpServletRequest request = new MockHttpServletRequest("POST", "/api/v1/articles");

        ResponseEntity<ErrorResponseDto> response = handler.handleUnexpected(
                new RuntimeException("database password leaked"),
                request
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
        assertThat(response.getBody()).isNotNull();
        assertThat(response.getBody().status()).isEqualTo(500);
        assertThat(response.getBody().error()).isEqualTo("Internal Server Error");
        assertThat(response.getBody().message()).isEqualTo("서버 내부 오류가 발생했습니다.");
        assertThat(response.getBody().path()).isEqualTo("/api/v1/articles");
    }
}
