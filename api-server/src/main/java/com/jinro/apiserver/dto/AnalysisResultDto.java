package com.jinro.apiserver.dto;

import com.jinro.apiserver.domain.AnalysisResult;
import lombok.Getter;

import java.time.ZonedDateTime;

@Getter
public class AnalysisResultDto {
    private final Long id;
    private final String modelUsed;
    private final Double sentimentScore;
    private final Double biasScore;
    private final Double factualityScore;
    private final String summary;
    private final ZonedDateTime analyzedAt;

    public AnalysisResultDto(AnalysisResult analysisResult) {
        this.id = analysisResult.getId();
        this.modelUsed = analysisResult.getModelUsed();
        this.sentimentScore = analysisResult.getSentimentScore();
        this.biasScore = analysisResult.getBiasScore();
        this.factualityScore = analysisResult.getFactualityScore();
        this.summary = analysisResult.getSummary();
        this.analyzedAt = analysisResult.getAnalyzedAt();
    }
}
