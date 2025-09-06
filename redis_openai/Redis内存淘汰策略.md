# 问题：Redis内存淘汰策略
回答如下：
「Redis内存淘汰策略」 请根据以下内容：
当内存不足时，Redis根据配置的淘汰策略（如noeviction、allkeys-lru、volatile-lru等）删除部分数据。LRU（最近最少使用）和LFU（最不经常使用）是常用策略。
 细化回答: 
 要求：1. 回答要详细，内容丰富，实践与理论结合！2. 采用总分总的文章思路！3、适当进行图示说明# Redis 内存淘汰策略（Eviction Policies）全解析

> **总分总**  
> 1️⃣ **总览** – 何为淘汰、Redis 内存模型、淘汰策略的必要性  
> 2️⃣ **细分** – 各种策略的原理、适用场景、配置方法、实践案例  
> 3️⃣ **总结** – 选型指南、监控与调优、常见坑与最佳实践

> 📌 **图示**  
> - 内存结构示意图  
> - 退役算法流程图  
> - 选型决策树

> ⚙️ **实践**  
> - 配置文件片段  
> - `redis-cli` 命令演示  
> - 监控脚本样例  

> 让我们一起把理论落地，真正做到 **“配置正确，运行无忧”。**

---

## 1️⃣ 总览：为什么需要淘汰？

### 1.1 Redis 的内存模型

```
┌─────────────────────────────┐
│  key  │  value  │  metadata │
│  ─────│─────────│────────────│
│  ...  │  ...    │  ...      │
└─────────────────────────────┘
```

- **maxmemory**：Redis 的内存上限（`--maxmemory` / `maxmemory` 配置项）。  
- **maxmemory-policy**：当内存使用达到上限时，Redis 如何做处理。

> **内存泄漏 vs. 内存溢出**  
> - *泄漏*：内存被占用却永不释放。  
> - *溢出*：已达到上限，需要主动清理。

### 1.2 淘汰的核心概念

| 术语 | 说明 |
|------|------|
| *eviction* | 内存溢出时删除数据 |
| *eviction policy* | 删除策略 |
| *maxmemory-policy* | 配置项 |
| *volatile* | 只淘汰设置了 `expire` 的键 |
| *allkeys* | 任意键都可淘汰 |

> **为什么要淘汰？**  
> - **保证稳定**：防止 `OOM`，保持服务可用。  
> - **节约成本**：避免在本机上跑满内存导致磁盘扩容。  
> - **提升响应**：淘汰热点不再占用内存，降低 GC/复制延迟。

---

## 2️⃣ 细分：淘汰策略一览

Redis 官方支持 7 种淘汰策略。下面从原理 → 适用场景 → 配置 → 实践 四个维度剖析。

> ⚠️ **配置示例**  
> ```yaml
> maxmemory: 2gb
> maxmemory-policy: allkeys-lru
> ```

| 策略 | 关键字 | 说明 | 适用场景 | 监控指标 |
|------|--------|------|----------|----------|
| noeviction | ❌ | 不淘汰，直接拒绝写 | 对写负载要求低、需要强一致性的业务 | `redis-cli INFO memory | grep oom` |
| allkeys-lru | 🔄 | 所有键，基于 LRU | 常用缓存、热点频繁更新 | `evicted_keys` |
| volatile-lru | 🔁 | 仅有过期键，基于 LRU | 只淘汰有 TTL 的键 | `evicted_keys` |
| allkeys-random | 🎲 | 所有键，随机淘汰 | 低功耗、键分布均匀 | `evicted_keys` |
| volatile-random | 🎲 | 仅过期键，随机淘汰 | 需要保持某些键长存 | `evicted_keys` |
| allkeys-lfu | 📉 | 所有键，基于 LFU | 访问频率不稳定的缓存 | `evicted_keys` |
| volatile-lfu | 📉 | 仅过期键，基于 LFU | 需要淘汰长久不活跃键 | `evicted_keys` |

> ### 2.1 LRU (Least Recently Used)

**原理**  
- Redis 通过 **“回环队列 + LRU 计数器”** 实现。  
- 每次键被访问，都会被插入到队列头部；当内存溢出时，从队列尾部（最久未使用）开始淘汰。

**图示**  

```
[head] <--- (访问频繁)   ----> [tail]
| key1 | key2 | ... | keyN |
```

- **时间复杂度**：O(1)  
- **内存开销**：每个键额外 8 字节（64‑bit 计数器）

**适用场景**  
- **热点缓存**：热点键访问频率高，LRU 能有效保留。  
- **读多写少**：写操作不太频繁，LRU 维护成本低。

**实践案例**  

```bash
# 开启 LRU
redis-cli CONFIG SET maxmemory 1gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru

# 查看淘汰统计
redis-cli INFO memory | grep evicted
```

> ### 2.2 LFU (Least Frequently Used)

**原理**  
- Redis 采用 **“LFU 计数桶”**（5×5 表），按 **频率** 而非时间淘汰。  
- 每访问一次，计数器递增；当计数器达到阈值后，自动降频（自下限 1），保持“近似” LFU。

**图示**  

```
┌─────────────┐
│  freq 1 -> 2│
│  freq 2 -> 3│
│  ...        │
└─────────────┘
```

- **时间复杂度**：O(log N) 但因计数桶优化，实际几乎 O(1)。  
- **内存开销**：比 LRU 低，计数器仅 2 位（0-3），但需要维护 4×4 表。

**适用场景**  
- **键分布稀疏**：热点键数量有限，但访问频率不稳定。  
- **写多读少**：写操作会触发计数，导致热点键频繁被保留。

**实践案例**  

```bash
redis-cli CONFIG SET maxmemory-policy allkeys-lfu
```

> ### 2.3 noeviction

**原理**  
- 当内存溢出时，写操作直接返回 `OOM` 错误。  
- 适合 *事务* 或 *强一致性* 场景，写入必定成功。

**适用场景**  
- **事务性缓存**：必须保留数据，避免被淘汰。  
- **写磁盘前置**：先将写入的数据持久化，再写到 Redis。

**实践案例**  

```bash
redis-cli CONFIG SET maxmemory-policy noeviction
```

> ### 2.4 其它策略（random, volatile‑XXX）

- **random**：随机淘汰，简单且开销极低。  
- **volatile‑XXX**：仅淘汰已设置 `EXPIRE` 的键，保护长寿命键。

> ⚙️ **配置技巧**  
> - **双策略**：先把业务键设置 `expire`，然后使用 `volatile-lru`，既保证热点又能释放无效键。  
> - **分区**：在单机多数据库时，给不同 DB 配置不同 `maxmemory-policy`，实现细粒度控制。

---

## 3️⃣ 总结：如何选型与调优？

### 3.1 选型决策树

```
┌─────────────────────┐
│ 内存已满？           │
├─────────────────────┤
│ ✔ 需要保留重要键？   │
├───────┬─────────────┤
│  ❌   │  ❌          │
│  │    │             │
│  │  使用 noeviction │
│  │  (写会 OOM)      │
│  │                 │
│  │                 │
│  ▼                 ▼
│  ❌ 需要随机淘汰   │
│  │  volatile-random │
│  │  allkeys-random  │
│  │                 │
│  ▼                 ▼
│  ✔ 需要基于访问   │
│  │  LRU 或 LFU     │
│  │  取决于热点分布 │
│  │  与频率特征    │
└─────────────────────┘
```

### 3.2 监控与指标

| 指标 | 说明 | 采集方式 |
|------|------|----------|
| `used_memory` | 当前占用内存 | `INFO memory` |
| `maxmemory` | 配置上限 | `CONFIG GET maxmemory` |
| `evicted_keys` | 已淘汰键数 | `INFO stats` |
| `expired_keys` | 已过期键数 | `INFO stats` |
| `keyspace_hits / keyspace_misses` | 访问命中率 | `INFO stats` |

> **监控脚本示例**（Bash）  

```bash
#!/usr/bin/env bash
REDIS_PORT=6379
REDIS_HOST=localhost

used=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT INFO memory | grep used_memory | awk -F: '{print $2}')
max=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT CONFIG GET maxmemory | tail -n1)
evicted=$(redis-cli -h $REDIS_HOST -p $REDIS_PORT INFO stats | grep evicted_keys | awk -F: '{print $2}')

echo "used: $used / max: $max | evicted: $evicted"
```

### 3.3 常见坑 & 建议

| 现象 | 原因 | 解决方案 |
|------|------|----------|
| 大量 OOM 错误 | `noeviction` + `maxmemory` 太低 | 调高 `maxmemory` 或改用 `volatile-lru` |
| 缓存命中率骤降 | 键被频繁淘汰 | 调高 `maxmemory` 或改用 `allkeys-lfu` |
| 内存泄漏 | 键未设置 expire | 使用 `volatile` 策略或手动 `DEL` |
| 复制延迟高 | 大量淘汰导致链路拥堵 | 采用 `volatile-ttl` + `maxmemory` |
| 监控不及时 | 未开启 `stats` | `CONFIG SET stats` |

---

## 4️⃣ 结束语

- **淘汰** 是 Redis 在高并发、高容量环境下保持稳定的核心手段。  
- **理论+实践** 的结合：先根据业务访问模式选策略，再通过监控与实验验证。  
- **持续迭代**：业务变化、流量波动，定期回顾淘汰策略与内存配置。

> **一句话总结**：  
> “**不要让内存成为瓶颈**，通过合适的淘汰策略把握热点，让 Redis 只存活最需要的那份数据。”  

祝你在 Redis 的海洋里，能让内存管理像行云流水般顺畅 🚀。