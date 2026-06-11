package com.jinro.apiserver.repository;

import com.jinro.apiserver.domain.AnalysisResult;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface AnalysisResultRepository extends JpaRepository<AnalysisResult, Long> {
    List<AnalysisResult> findByArticleId(Long articleId);
}
