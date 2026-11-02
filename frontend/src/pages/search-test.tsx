/**
 * H4 · 检索测试页：query + top_k + 可选过滤 → 命中列表（score/来源/页码）
 * + 分项耗时（embedding / search / total）。
 */
import { useState } from "react";
import {
  Button,
  Card,
  Empty,
  Input,
  InputNumber,
  List,
  message,
  Space,
  Statistic,
  Tag,
  Typography,
} from "antd";
import { SearchOutlined } from "@ant-design/icons";
import { searchApi, errorMessage, type SearchTestResponse } from "../api";

export default function SearchTestPage() {
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(5);
  const [docIdFilter, setDocIdFilter] = useState("");
  const [result, setResult] = useState<SearchTestResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    if (!query.trim()) {
      message.warning("请输入检索内容");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const filters = docIdFilter.trim() ? { doc_id: docIdFilter.trim() } : undefined;
      const r = await searchApi.test({ query: query.trim(), top_k: topK, filters });
      setResult(r);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card title="检索测试">
      <Space direction="vertical" style={{ width: "100%" }} size={12}>
        <Input.TextArea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="输入要检索的内容（向量化后与文档 chunk 比对）"
          autoSize={{ minRows: 2, maxRows: 5 }}
          onPressEnter={() => void run()}
        />
        <Space wrap>
          <span>top_k</span>
          <InputNumber min={1} max={20} value={topK} onChange={(v) => setTopK(v ?? 5)} />
          <Input
            allowClear
            style={{ width: 300 }}
            placeholder="可选：限定 doc_id"
            value={docIdFilter}
            onChange={(e) => setDocIdFilter(e.target.value)}
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            loading={loading}
            onClick={() => void run()}
          >
            检索
          </Button>
        </Space>
      </Space>

      {result && (
        <>
          <Space wrap size={24} style={{ margin: "20px 0 8px" }}>
            <Statistic title="Embedding 耗时" value={result.took_embedding_ms} suffix="ms" />
            <Statistic title="向量检索耗时" value={result.took_search_ms} suffix="ms" />
            <Statistic title="总耗时" value={result.took_total_ms} suffix="ms" />
            <Statistic title="命中" value={result.hits.length} suffix={`/ top_${topK}`} />
          </Space>

          {result.hits.length === 0 ? (
            <Empty description="无命中结果" style={{ marginTop: 24 }} />
          ) : (
            <List
              dataSource={result.hits}
              renderItem={(hit, idx) => (
                <List.Item key={idx}>
                  <div style={{ width: "100%" }}>
                    <Space wrap style={{ marginBottom: 4 }}>
                      <Tag color="volcano">score {hit.score.toFixed(4)}</Tag>
                      <Tag color="geekblue">
                        doc {hit.doc_id.slice(0, 8)}…
                      </Tag>
                      {hit.version !== null && <Tag>v{hit.version}</Tag>}
                      {hit.page !== null && <Tag color="blue">第 {hit.page} 页</Tag>}
                      <Tag>chunk #{String(hit.metadata?.chunk_index ?? "—")}</Tag>
                    </Space>
                    <Typography.Paragraph style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}>
                      {hit.text}
                    </Typography.Paragraph>
                  </div>
                </List.Item>
              )}
            />
          )}
        </>
      )}

      {!result && !loading && (
        <Empty description="输入内容后点击「检索」" style={{ marginTop: 32 }} />
      )}
    </Card>
  );
}
