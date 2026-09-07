package com.jinro.apiserver.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;
import java.util.regex.Pattern;

@ConfigurationProperties(prefix = "app.article-source")
public class ArticleSourceProperties {

    private static final Pattern HOST_PATTERN = Pattern.compile(
            "(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\\.)+[a-z]{2,63}");

    private List<String> hosts = List.of("news.sbs.co.kr");

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        if (hosts == null) {
            throw new IllegalArgumentException("app.article-source.hosts must not be null");
        }
        var normalizedHosts = hosts.stream()
                .map(String::trim)
                .map(String::toLowerCase)
                .filter(host -> !host.isBlank())
                .peek(host -> {
                    if (!HOST_PATTERN.matcher(host).matches()) {
                        throw new IllegalArgumentException("Invalid article source host");
                    }
                })
                .distinct()
                .toList();
        this.hosts = normalizedHosts.isEmpty() ? List.of("news.sbs.co.kr") : normalizedHosts;
    }
}
