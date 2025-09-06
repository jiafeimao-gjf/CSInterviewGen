# 问题：Redis字典结构：哈希表实现
回答如下：
「Redis字典结构：哈希表实现」 请根据以下内容：
Redis使用字典（dict）结构存储键值对，底层是哈希表+链表的组合。字典包含两个entry数组，一个用于正常操作，一个用于扩容时转移数据，实现渐进式扩容，避免服务中断。
 细化回答: 
 要求：1. 回答要详细，内容丰富，实践与理论结合！2. 采用总分总的文章思路！3、适当进行图示说明# Redis 字典（dict）结构——哈希表实现详解  

> **目标**  
> 1. 结合理论与实践，系统阐述 Redis 内部字典（dict）的实现细节。  
> 2. 采用「总‑分‑总」的文章架构，帮助读者从宏观到微观再回到整体。  
> 3. 用图示直观展示典型的哈希表与渐进式扩容过程。

---

## 1. 总览：Redis 为何要用「dict」？

- **键值对存储的核心**  
  Redis 内部所有 `String`, `Hash`, `Set`, `Sorted Set` 等数据结构最终都需要把键映射到对应的 **value**，实现这一功能的最直接方式就是 **哈希表**。  
- **字典的两层抽象**  
  * **dict**：对外的“字典”对象，负责操作接口（`dictAdd`, `dictFind` 等）。  
  * **dictEntry**：存储单条键值对的内部结构。  
- **双数组 + 渐进式扩容**  
  传统哈希表在扩容时会一次性拷贝全部数据，导致服务短暂不可用。Redis 通过 **两个哈希表**（`ht[0]` 与 `ht[1]`）配合 **rehashIdx** 实现 **渐进式扩容**，保证任意时间点都可以继续服务。

---

## 2. 分析：dict 的底层结构

### 2.1 主要结构体

```c
/* dictEntry: 单条键值对 */
typedef struct dictEntry {
    void *key;          /* 指向键的指针 */
    void *value;        /* 指向值的指针 */
    struct dictEntry *next; /* 链表指针，用于解决哈希冲突 */
} dictEntry;

/* dictHashTable: 单个哈希表 */
typedef struct dictHashTable {
    dictEntry **table;   /* 桶数组，长度为 power‑of‑two */
    unsigned long size;  /* 桶数组长度 */
    unsigned long sizemask; /* size-1，用于快速取模 */
    unsigned long used;  /* 当前使用的元素个数 */
} dictHashTable;

/* dict: 整个字典 */
typedef struct dict {
    dictType *type;          /* 定义键/值的类型、哈希函数等 */
    dictHashTable ht[2];     /* ht[0]：正常表，ht[1]：扩容表 */
    long rehashidx;          /* -1 表示未在扩容，>=0 表示当前正处于 rehashing 阶段 */
    int (*equal)();          /* 键比较函数 */
    int (*hashFunction)();   /* 哈希函数 */
    unsigned long (*keyDup)();
    unsigned long (*valDup)();
} dict;
```

> **核心点**  
> - `size` 取 **2 的幂**，`sizemask = size-1`，可以用位运算快速得到 `hash % size`。  
> - `next` 形成链表实现 **拉链法**（Separate Chaining）处理冲突。  
> - `ht[1]` 与 `rehashidx` 共同完成渐进式扩容。

### 2.2 哈希函数

Redis 默认采用 **MurmurHash2**（或改进版）：

```c
unsigned int dictGenHashFunction(const void *key, int len) {
    // 具体实现略...
}
```

> 32 位哈希值，足以覆盖 `size` 的范围，且分布均匀。

---

## 3. 细化：从插入到渐进式扩容的完整流程

### 3.1 正常插入（非扩容阶段）

1. **计算哈希**  
   `hash = dict->hashFunction(key, len);`

2. **定位桶**  
   `index = hash & dict->ht[0].sizemask;`

3. **插入链表**  
   ```c
   dictEntry *he = dictCreateEntry(key, value);
   he->next = dict->ht[0].table[index];
   dict->ht[0].table[index] = he;
   dict->ht[0].used++;
   ```

4. **检查扩容阈值**  
   ```c
   if (!dictIsRehashing(dict) && dict->ht[0].used > dict->ht[0].size * 1.0) {
       dictExpand(dict, dict->ht[0].size * 2);
   }
   ```

### 3.2 开始扩容

- `dictExpand` 分配新的 `ht[1]`（大小为原来的 2 倍），`rehashidx = 0`。  
- 此时 **读写仍在 `ht[0]`**，但后续每次操作都会先执行 **`dictRehash`**。

### 3.3 渐进式迁移（`dictRehash`）

```c
int dictRehash(dict *d, int n) {
    while (n--) {
        if (d->rehashidx == d->ht[0].size) {
            freeHashTable(d->ht[0]);
            d->ht[0] = d->ht[1];
            d->ht[1].table = NULL;
            d->rehashidx = -1;
            return 0; // 迁移完成
        }
        // 取出当前桶链表
        dictEntry *entry = d->ht[0].table[d->rehashidx];
        d->ht[0].table[d->rehashidx] = NULL;
        while (entry) {
            dictEntry *next = entry->next;
            // 重新哈希到新表
            unsigned int h = d->hashFunction(entry->key, d->keyLen);
            unsigned int index = h & d->ht[1].sizemask;
            entry->next = d->ht[1].table[index];
            d->ht[1].table[index] = entry;
            d->ht[0].used--; d->ht[1].used++;
            entry = next;
        }
        d->rehashidx++;
    }
    return 1; // 仍在迁移
}
```

- **迁移步长**：每个调用迁移 **n** 个桶（默认 1），把整桶链表搬迁到新表。  
- **并发安全**：Redis 单线程模型保证在迁移期间没有其他线程干扰。

### 3.4 查询与删除的双表检索

```c
dictEntry *dictFind(dict *d, const void *key) {
    if (dictIsRehashing(d)) dictRehash(d, 1);
    unsigned int h = d->hashFunction(key, d->keyLen);
    unsigned int idx0 = h & d->ht[0].sizemask;
    dictEntry *he = d->ht[0].table[idx0];
    while (he) { if (he->key == key) return he; he = he->next; }
    if (dictIsRehashing(d)) { // 需要再检查新表
        unsigned int idx1 = h & d->ht[1].sizemask;
        he = d->ht[1].table[idx1];
        while (he) { if (he->key == key) return he; he = he->next; }
    }
    return NULL;
}
```

- **查询**：先查旧表，再查新表（若正在扩容）。  
- **删除**：同样先查旧表，再查新表。

---

## 4. 图示：从正常状态到扩容状态

### 4.1 正常哈希表

```
hash table (size = 8)
┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
│ 0   │ 1   │ 2   │ 3   │ 4   │ 5   │ 6   │ 7   │
│-----│-----│-----│-----│-----│-----│-----│-----│
│ A→B │     │ C   │     │ D→E │     │     │     │
└─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
```

- **键 A、B** 位于桶 0，使用链表解决冲突。  
- **键 C**、**键 D、E** 分别在桶 2 与 4。

### 4.2 开始扩容：两个哈希表

```
ht[0] (size=8)   |   ht[1] (size=16, 迁移中)
┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐   ┌─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┬─────┐
│ 0   │ 1   │ 2   │ 3   │ 4   │ 5   │ 6   │ 7   │   │ 0   │ 1   │ 2   │ 3   │ 4   │ 5   │ 6   │ 7   │ 8   │ 9   │10   │11   │12   │13   │14   │15   │
│-----│-----│-----│-----│-----│-----│-----│-----│   │-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│-----│
│ A→B │     │ C   │     │     │     │     │     │   │     │     │     │     │     │     │     │     │     │     │     │     │     │     │     │     │
└─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘   └─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┴─────┘
```

- **rehashidx**：当前迁移到 `ht[1]` 的桶索引（此图假设已经迁移到桶 0）。  
- **迁移完成后**：`ht[0]` 被替换为 `ht[1]`，`ht[1]` 被清空。

### 4.3 渐进式迁移示意

```
Step 0: rehashidx = 0
Step 1: 迁移桶 0
Step 2: 迁移桶 1
...
```

> 每一步只迁移 **一个桶**（或若干条链表条目），保证单次 CPU 占用极低。

---

## 5. 结合实践：dict 在 Redis 代码中的运用

| 场景 | dict 用法 |
|------|-----------|
| **全局键空间** | `dict *dict` 存放所有 `RedisObject*`（key → value）。 |
| **Hash 字段** | `dict *hdict` 存放 hash 字段 → value。 |
| **Set** | `dict *set` 存放 set 元素。 |
| **Sorted Set** | `dict *zdict` 存放元素 → score，配合 skiplist 维护排序。 |

### 5.1 典型调用流程

```c
/* 插入全局键 */
dictAdd(globaldict, keyObj, valObj);

/* 查找键 */
dictEntry *e = dictFind(globaldict, keyObj);

/* 删除键 */
dictDelete(globaldict, keyObj);
```

### 5.2 代码级实现小结

- `dictAdd` → `dictAddRaw` → `dictExpandIfNeeded` → `dictInsert`  
- `dictFind` → `dictLookupRead`  
- `dictDelete` → `dictDeleteGeneric`  
- 所有操作前后都会调用 `dictRehash`（若处于迁移），保证 **渐进式**。

---

## 6. 总结：为什么 Redis 采用双表 + 渐进式扩容？

| 维度 | 传统哈希表 | Redis dict |
|------|-----------|------------|
| **扩容方式** | 立即拷贝全部数据 | 逐桶迁移 |
| **服务中断** | 可能出现短暂停机 | 彻底消除 |
| **复杂度** | O(1) 期望，O(n) 触发 | O(1) 期望，O(1) 迁移步长 |
| **实现难度** | 简单 | 需要维护两张表、rehashIdx |
| **内存占用** | 临时占用两倍 | 只占用迁移阶段的 2× |
| **适用性** | 单线程 | 单线程/多线程均可，Redis 采用单线程模型 |

- **性能与可用性并存**：在单线程环境下，Redis 通过 **每次只迁移一个桶**，将扩容成本摊薄到毫秒级。  
- **扩容阈值**：默认 `load_factor = 1.0`，即 `used > size` 时触发扩容，确保哈希表保持 **O(1)** 的平均访问速度。  
- **可扩展性**：`dict` 结构被广泛复用，从顶层 keyspace 到内部数据类型，展示了 Redis 代码的高内聚低耦合设计。

---

### 结束语

Redis 的 dict 结构，虽然表面上看只是一个哈希表 + 链表，但背后隐藏的 **渐进式扩容机制**、**双表并行迁移**、**轻量级链表冲突解决** 等设计细节，使其在高并发、内存敏感的环境下仍能保持极佳的性能与可靠性。理解这一结构不仅帮助你深入 Redis 的内部实现，也为你在自己的项目中构建高效键值存储提供了宝贵经验。