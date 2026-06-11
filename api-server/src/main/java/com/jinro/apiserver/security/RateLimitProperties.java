package com.jinro.apiserver.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.rate-limit")
public class RateLimitProperties {

    private boolean enabled = true;
    private int limit = 60;
    private long windowSeconds = 60;
    private int cleanupThreshold = 1000;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getLimit() {
        return limit;
    }

    public void setLimit(int limit) {
        if (limit < 1) {
            throw new IllegalArgumentException("app.rate-limit.limit must be greater than 0.");
        }
        this.limit = limit;
    }

    public long getWindowSeconds() {
        return windowSeconds;
    }

    public void setWindowSeconds(long windowSeconds) {
        if (windowSeconds < 1) {
            throw new IllegalArgumentException("app.rate-limit.window-seconds must be greater than 0.");
        }
        this.windowSeconds = windowSeconds;
    }

    public int getCleanupThreshold() {
        return cleanupThreshold;
    }

    public void setCleanupThreshold(int cleanupThreshold) {
        if (cleanupThreshold < 1) {
            throw new IllegalArgumentException("app.rate-limit.cleanup-threshold must be greater than 0.");
        }
        this.cleanupThreshold = cleanupThreshold;
    }
}
