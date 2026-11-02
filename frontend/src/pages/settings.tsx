/**
 * H5 · 设置页（MVP 最小）：只读展示默认 Embedding 模型配置与切分参数。
 */
import { useEffect, useState } from "react";
import { Card, Col, Descriptions, Empty, message, Row, Skeleton } from "antd";
import { settingsApi, errorMessage, type EffectiveSettings } from "../api";

export default function SettingsPage() {
  const [data, setData] = useState<EffectiveSettings | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    settingsApi
      .effective()
      .then((r) => {
        if (mounted) setData(r);
      })
      .catch((err) => message.error(errorMessage(err)))
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) return <Card title="设置" loading />;

  return (
    <Card title="设置">
      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card size="small" title="默认 Embedding 模型">
            {data?.embedding_model ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="名称">{data.embedding_model.name}</Descriptions.Item>
                <Descriptions.Item label="Provider">{data.embedding_model.provider}</Descriptions.Item>
                <Descriptions.Item label="模型">{data.embedding_model.model_name}</Descriptions.Item>
                <Descriptions.Item label="维度">{data.embedding_model.dimension}</Descriptions.Item>
                <Descriptions.Item label="默认">
                  {data.embedding_model.is_default ? "是" : "否"}
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <Empty description="未配置默认模型" />
            )}
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card size="small" title="切分参数（只读）">
            {data ? (
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="chunk_size">
                  {data.chunking.chunk_size} tokens
                </Descriptions.Item>
                <Descriptions.Item label="chunk_overlap">
                  {data.chunking.chunk_overlap} tokens
                </Descriptions.Item>
              </Descriptions>
            ) : (
              <Skeleton active paragraph={{ rows: 2 }} />
            )}
          </Card>
        </Col>
      </Row>
    </Card>
  );
}