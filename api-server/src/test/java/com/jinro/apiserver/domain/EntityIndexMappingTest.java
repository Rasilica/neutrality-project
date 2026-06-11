package com.jinro.apiserver.domain;

import jakarta.persistence.Index;
import jakarta.persistence.Table;
import org.junit.jupiter.api.Test;

import java.util.Arrays;

import static org.assertj.core.api.Assertions.assertThat;

class EntityIndexMappingTest {

    @Test
    void articleEntityDeclaresDatabaseIndexes() {
        Table table = Article.class.getAnnotation(Table.class);

        assertThat(indexColumnList(table, "idx_articles_source_published_at"))
                .isEqualTo("source_id, published_at DESC");
        assertThat(indexColumnList(table, "idx_articles_source_id"))
                .isEqualTo("source_id");
        assertThat(indexColumnList(table, "idx_articles_published_at"))
                .isEqualTo("published_at DESC");
    }

    @Test
    void analysisResultEntityDeclaresDatabaseIndexes() {
        Table table = AnalysisResult.class.getAnnotation(Table.class);

        assertThat(indexColumnList(table, "idx_analysis_results_article_model"))
                .isEqualTo("article_id, model_used");
        assertThat(indexColumnList(table, "idx_analysis_results_article_id"))
                .isEqualTo("article_id");
    }

    private String indexColumnList(Table table, String indexName) {
        return Arrays.stream(table.indexes())
                .filter(index -> indexName.equals(index.name()))
                .map(Index::columnList)
                .findFirst()
                .orElse("");
    }
}
