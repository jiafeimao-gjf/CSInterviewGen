# 问题：Redis集群：哈希槽分配
回答如下：
「Redis集群：哈希槽分配」 请根据以下内容：
Redis集群将数据分为16384个哈希槽，每个槽分配给一个节点管理。通过CRC16算法计算key的哈希值，确定槽位置。集群自动处理节点故障和数据迁移，实现高可用和水平扩展。
 细化回答: 
 要求：1. 回答要详细，内容丰富，实践与理论结合！2. 采用总分总的文章思路！3、适当进行图示说明# Redis 集群哈希槽分配详解  

> **Redis Cluster** 通过 **16384** 个哈希槽（hash slots）来把键（key）映射到集群中的节点。  
> 本文结合理论与实践，细化哈希槽的分配原理、关键算法、迁移机制以及常见操作命令，帮助你快速搭建、调优与维护 Redis 集群。

---

## 一、整体结构（总论）

1. **集群目标**  
   - **水平扩展**：通过增删节点动态扩容/缩容。  
   - **高可用**：主从同步与故障转移（failover）。  
   - **自动化**：集群内部自动完成槽迁移与节点健康检查。  

2. **核心概念**  
   - **节点（Node）**：主节点（master）+从节点（replica）。  
   - **槽（Slot）**：键的哈希值映射到的 0–16383 之间的整数。  
   - **CRC16**：计算哈希值的算法。  
   - **hash tag**：通过 `{}` 指定键的子串参与哈希，保证同一 hash tag 的键落在同一槽。  

3. **数据流**  
   - 客户端 → **解析 key** → **CRC16 → 计算槽** → **路由至对应 master**  
   - 若 master 故障 → 复制节点提升为 master → 重新分配槽  
   - 添加节点 → 迁移部分槽 → 重新平衡

> **图示 1：Redis 集群基本架构**  
> ```
> ┌───────────────┐
> │   Client      │
> └───────┬───────┘
>         │
> ┌───────▼───────┐
> │  Redis Cluster│
> │   (master+rep)│
> └───────┬───────┘
>         │
>   ┌─────▼─────┐
>   │   Slots   │ (0–16383)
>   └───────────┘
> ```

---

## 二、哈希槽计算与分配（细化论）

### 1. 哈希槽的生成
- **CRC16 算法**  
  ```c
  uint16_t crc16(const void *data, size_t len);
  ```
- **槽号 = CRC16(key) mod 16384**

> **图示 2：CRC16 → 槽号**  
> ```
> key ──► CRC16(value) ──► mod 16384 ──► slot
> ```

- **hash tag**：如果 key 里包含 `{}`，则仅对大括号中的子串做 CRC16，保证同一 tag 的键在同一槽。  
  - 例：`user:{123}:profile` → 只取 `123`

### 2. 节点槽映射
- 每个 **master** 节点负责 **若干连续或非连续的槽**。  
- 在 `cluster nodes` 输出中可见 `slots [0-5460] [5461-10922] …`  
- **槽分布** 统计示例（5 节点）：

| Node | Slots（起止） | 占比 |
|------|--------------|------|
| A    | 0–5460      | 33% |
| B    | 5461–10922  | 33% |
| C    | 10923–16383 | 33% |
| D    | 0–5460      | 33% |
| E    | 5461–10922  | 33% |

> **图示 3：槽分布示意**  
> ```
> 0-5460    ──> Node A
> 5461-10922 ──> Node B
> 10923-16383 ──> Node C
> ```

### 3. 添加节点的槽迁移
- **步骤**  
  1. **MEET**：新节点加入集群 (`redis-cli --cluster meet`)  
  2. **Assign Slots**：使用 `redis-cli --cluster add-node` → `redis-cli --cluster reshard`  
  3. **Reshard**：脚本逐步迁移槽。  
- **迁移原理**  
  - `CLUSTER ADDSLOTS` / `CLUSTER DELSLOTS` 让 master 接受/放弃槽。  
  - 数据迁移是 **复制** → **删除** → **同步**，不影响客户端读写（读写会自动重定向）。

> **图示 4：槽迁移流程**  
> ```
> NodeX ──► 迁移槽 → NodeY
>     │          │
>     └─ 复制 → 删除
> ```

### 4. 节点故障与自动迁移
- **监控**：`CLUSTER NODES` 中 `fail` 状态。  
- **自动 failover**：  
  1. 主节点宕机 → 从节点提升。  
  2. 旧主节点重新上线 → 重新成为从节点。  
  3. 旧主节点的槽自动重新分配。  
- **手动恢复**：使用 `redis-cli --cluster rebalance` 进行手动槽重新平衡。

> **图示 5：主从切换与槽迁移**  
> ```
> Master A ──> 失效
>    │
>    └─> Replica B 升级为 Master
>    │
>    └─> 旧主 A 变为 Replica B 的从节点
> ```

---

## 三、实践操作（案例）

### 1. 快速搭建 3 节点集群

```bash
# 假设已有 3 台机器，端口 7000~7002
redis-server --cluster-enabled yes --cluster-config-file nodes.conf --cluster-node-timeout 5000 --appendonly yes
```

```bash
# 在任意一台机器执行
redis-cli --cluster create 192.168.1.101:7000 192.168.1.102:7001 192.168.1.103:7002 --cluster-replicas 0
```

### 2. 查看槽分布

```bash
redis-cli -p 7000 cluster nodes
redis-cli -p 7000 cluster slots
```

### 3. 添加副本节点

```bash
# 先把副本机器加入集群
redis-cli --cluster add-node 192.168.1.104:7003 192.168.1.101:7000
# 让每个 master 有一个 replica
redis-cli --cluster rebalance 192.168.1.101:7000
```

### 4. 迁移槽

```bash
redis-cli --cluster reshard 192.168.1.101:7000 --from-node 7000 --to-node 7001 --num-migrate 2000
```

### 5. 故障演示

```bash
# 关闭主节点
kill $(ps -ef | grep redis | grep 7000 | awk '{print $2}')
# 自动 failover
redis-cli -p 7001 cluster info   # 查看 state=ok
```

---

## 四、常见问题 & 解决方案

| 现象 | 可能原因 | 解决办法 |
|------|----------|----------|
| `MOVED` 重定向次数过多 | 集群未完成 `rescan` 或 `rebalance` | 等待迁移完成；检查 `CLUSTER SLOTS` |
| 数据丢失 | 手动迁移未同步完成 | 使用 `--cluster migrate` 或 `--cluster reshard` |
| 节点负载不均 | 迁移策略不当 | `--cluster rebalance` + `--cluster-slave-assign` |
| 性能瓶颈 | 单个节点 I/O 限制 | 水平扩容，使用 SSD |
| 超时 | 网络延迟高 | 调整 `cluster-node-timeout` |

---

## 五、总结（总论）

- **Redis Cluster** 通过 **16384** 个哈希槽实现键到节点的确定性映射。  
- **CRC16** + **mod 16384** 为核心计算机制，保证键分布均匀。  
- **槽迁移** 与 **故障转移** 是集群的自适应核心，使用 `CLUSTER` 系列命令可以手动或自动完成。  
- **hash tag** 为分布式事务或锁提供了保证同一槽的手段。  
- 在实际运维中，**监控**（`cluster info`、`cluster nodes`）、**备份**（RDB/AOF）和**安全**（ACL、SSL）是不可或缺的配套。

> **图示 6：完整集群生命周期**  
> ```
> 初始化 ──> 节点加入 ──> 负载平衡 ──> 故障转移 ──> 扩容/缩容
> ```

> **最终落脚点**  
> - 通过对 **哈希槽** 的深入理解，你可以更好地规划集群结构，提前预判热点、优化复制和迁移策略，进一步提升 Redis 集群的 **可用性** 与 **伸缩性**。  

祝你在 Redis 集群的旅程中玩得开心、运维顺利！