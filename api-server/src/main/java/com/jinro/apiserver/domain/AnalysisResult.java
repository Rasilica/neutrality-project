package com.jinro.apiserver.domain;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.ZonedDateTime;

@Entity
@Table(
        name = "analysis_results",
        indexes = {
                @Index(name = "idx_analysis_results_article_id", columnList = "article_id"),
                @Index(name = "idx_analysis_results_article_model", columnList = "article_id, model_used")
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class AnalysisResult {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "article_id", nullable = false)
    private Article article;

    @Column(name = "model_used", nullable = false, length = 50)
    private String modelUsed;

    @Column(name = "sentiment_score")
    private Double sentimentScore;

    @Column(name = "bias_score")
    private Double biasScore;

    @Column(name = "factuality_score")
    private Double factualityScore;

    @Column(columnDefinition = "TEXT")
    private String summary;

    @Column(name = "raw_response", columnDefinition = "jsonb")
    private String rawResponse;

    @Column(name = "analyzed_at", nullable = false, updatable = false)
    private ZonedDateTime analyzedAt;
}
