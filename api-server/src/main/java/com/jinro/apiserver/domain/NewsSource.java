package com.jinro.apiserver.domain;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.ZonedDateTime;

@Entity
@Table(name = "news_sources")
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class NewsSource {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 100)
    private String name;

    @Column(name = "rss_url", nullable = false, unique = true, columnDefinition = "TEXT")
    private String rssUrl;

    @Column(name = "bias_label", length = 20)
    private String biasLabel;

    @Column(name = "created_at", nullable = false, updatable = false)
    private ZonedDateTime createdAt;
}
