from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictAnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ArticleAnalysisPayload(StrictAnalysisPayload):
    sentiment_score: float = Field(ge=-1.0, le=1.0)
    bias_score: float = Field(ge=0.0, le=1.0)
    factuality_score: float = Field(ge=0.0, le=1.0)
    summary: str = Field(min_length=1, max_length=4000)


class CommentAnalysisPayload(StrictAnalysisPayload):
    avg_sentiment: float = Field(ge=-1.0, le=1.0)
    positive_ratio: float = Field(ge=0.0, le=1.0)
    negative_ratio: float = Field(ge=0.0, le=1.0)
    neutral_ratio: float = Field(ge=0.0, le=1.0)
    public_opinion: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def ratios_sum_to_one(self):
        ratio_sum = self.positive_ratio + self.negative_ratio + self.neutral_ratio
        if abs(ratio_sum - 1.0) > 0.02:
            raise ValueError("comment ratios must sum to 1.0 within a 0.02 tolerance")
        return self
