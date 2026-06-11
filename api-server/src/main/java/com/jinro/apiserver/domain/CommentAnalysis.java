package com.jinro.apiserver.domain;

import jakarta.persistence.*;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.ZonedDateTime;

@Entity
@Table(
        name = "comment_analysis",
        indexes = {
                @Index(name = "idx_comment_analysis_article_id", columnList = "article_id")
        }
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class CommentAnalysis {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "article_id", nullable = false, unique = true)
    private Article article;

    @Column(name = "total_comments")
    private Integer totalComments;

    @Column(name = "avg_sentiment")
    private Double avgSentiment;

    @Column(name = "positive_ratio")
    private Double positiveRatio;

    @Column(name = "negative_ratio")
    private Double negativeRatio;

    @Column(name = "neutral_ratio")
    private Double neutralRatio;

    @Column(name = "public_opinion", columnDefinition = "TEXT")
    private String publicOpinion;

    @Column(name = "raw_response", columnDefinition = "jsonb")
    private String rawResponse;

    @Column(name = "analyzed_at", nullable = false, updatable = false)
    private ZonedDateTime analyzedAt;
}
