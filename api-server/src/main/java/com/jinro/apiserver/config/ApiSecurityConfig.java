package com.jinro.apiserver.config;

import com.jinro.apiserver.security.ApiSecurityProperties;
import com.jinro.apiserver.security.RateLimitProperties;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
@RequiredArgsConstructor
@EnableConfigurationProperties({
        ApiSecurityProperties.class,
        RateLimitProperties.class
})
public class ApiSecurityConfig implements WebMvcConfigurer {

    private final ApiSecurityProperties apiSecurityProperties;

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/v1/**")
                .allowedOrigins(apiSecurityProperties.getAllowedOrigins().toArray(String[]::new))
                .allowedMethods(apiSecurityProperties.getAllowedMethods().toArray(String[]::new))
                .allowedHeaders("Accept", "Content-Type", "Origin", "Authorization", "X-Requested-With")
                .exposedHeaders("X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After")
                .allowCredentials(false)
                .maxAge(apiSecurityProperties.getCorsMaxAgeSeconds());
    }
}
