/**
 * M4 · 监控大盘：健康状态卡（依赖探活 + 告警）+ 任务统计 + token 成本曲线。
 * 数据源：/health/detail（M3）、/stats/costs（M2）；指标口径与 /api/metrics 一致。
 */
import { useEffect, useState } from "react";
import {
  Card,
  Col,
  message,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import { opsApi, errorMessage, type HealthDetail, type CostSummary } from "../api";

function statusTag(status: string) {
  return status === "ok" ? <Tag color="green">健康</Tag> : <Tag color="red">降级</Tag>;
}

function HealthCard() {
  const [detail, setDetail] = useState<HealthDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    const load = () =>
      opsApi
        .healthDetail()
        .then((d) => {
          if (mounted) setDetail(d);
        })
        .catch((err) => message.error(errorMessage(err)))
        .finally(() => {
          if (mounted) setLoading(false);
        });
    void load();
    const timer = window.setInterval(load, 30_000); // 30s auto refresh
    return () => {
      mounted = false;
      window.clearInterval(timer);
    };
  }, []);

  if (loading && !detail) return <Card title="系统健康" loading />;
  if (!detail) return null;

  return (
    <Card
      title={
        <Space size={8}>
          <span>系统健康</span>
          {statusTag(detail.status)}
        </Space>
      }
      size="small"
    >
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Statistic title="文档总数" value={detail.gauges.documents_total} />
        </Col>
        <Col span={6}>
          <Statistic
            title="队列积压"
            value={detail.gauges.queue_depth}
            valueStyle={detail.gauges.queue_depth > 50 ? { color: "#cf1322" } : undefined}
          />
        </Col>
        <Col span={6}>
          <Statistic title="24h 失败任务" value={detail.gauges.jobs_failed_24h} />
        </Col>
        <Col span={6}>
          <Statistic title="24h 完成任务" value={detail.gauges.jobs_settled_24h} />
        </Col>
      </Row>
      <Row gutter={[16, 0]} style={{ marginTop: 16 }}>
        {Object.entries(detail.checks).map(([name, c]) => (
          <Col key={name} span={8}>
            <Space size={6}>
              {c.ok ? <Tag color="green">{name} ✓</Tag> : <Tag color="red">{name} ✗</Tag>}
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {c.detail} {c.elapsed_ms !== undefined ? `(${c.elapsed_ms}ms)` : ""}
              </Typography.Text>
            </Space>
          </Col>
        ))}
      </Row>
      {detail.alerts.length > 0 && (
        <div style={{ marginTop: 12 }}>
          {detail.alerts.map((a) => (
            <Tag key={a.code} color="red">
              {a.code}: {a.detail}
            </Tag>
          ))}
        </div>
      )}
    </Card>
  );
}

function CostCard() {
  const [data, setData] = useState<CostSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    opsApi
      .costs({ days: 30 })
      .then(setData)
      .catch((err) => message.error(errorMessage(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading && !data) return <Card title="Token 成本（近 30 天）" loading />;
  if (!data) return null;

  const maxTokens = Math.max(1, ...data.days.map((d) => d.tokens));

  return (
    <Card size="small" title="Token 成本（近 30 天，embed 步骤记账）">
      <Row gutter={[16, 16]}>
        <Col span={8}>
          <Statistic title="累计 tokens" value={data.total_tokens} />
        </Col>
        <Col span={8}>
          <Statistic title="embed 调用次数" value={data.embed_calls} />
        </Col>
        <Col span={8}>
          <Statistic title="有消耗天数" value={data.days.filter((d) => d.tokens > 0).length} />
        </Col>
      </Row>
      <div style={{ marginTop: 16 }}>
        {data.days.length === 0 ? (
          <Typography.Text type="secondary">暂无 embed 记录</Typography.Text>
        ) : (
          <Table
            rowKey="day"
            size="small"
            pagination={false}
            dataSource={data.days}
            columns={[
              { title: "日期", dataIndex: "day", width: 120 },
              {
                title: "tokens 消耗",
                dataIndex: "tokens",
                render: (v: number) => (
                  <Space size={8}>
                    <div
                      style={{
                        width: Math.max(4, (v / maxTokens) * 220),
                        height: 10,
                        background: "#1677ff",
                        borderRadius: 2,
                      }}
                    />
                    <span>{v.toLocaleString()}</span>
                  </Space>
                ),
              },
              { title: "调用次数", dataIndex: "embed_calls", width: 100 },
            ]}
          />
        )}
      </div>
    </Card>
  );
}

export default function MonitoringPage() {
  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <HealthCard />
      <CostCard />
    </Space>
  );
}
