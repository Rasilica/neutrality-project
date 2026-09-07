package com.jinro.apiserver.security;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.util.List;

@ConfigurationProperties(prefix = "app.article-source")
public class ArticleSourceProperties {

    private List<String> hosts = List.of("news.sbs.co.kr");

    public List<String> getHosts() {
        return hosts;
    }

    public void setHosts(List<String> hosts) {
        var normalizedHosts = hosts.stream()
                .map(String::trim)
                .map(String::toLowerCase)
                .filter(host -> !host.isBlank())
                .distinct()
                .toList();
        this.hosts = normalizedHosts.isEmpty() ? List.of("news.sbs.co.kr") : normalizedHosts;
    }
}
