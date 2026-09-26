"""Condensed Staff/Lead SWE interview curriculum.

This file IS the definition of done. Every track lists exactly what must be
finished; the app just tracks it. Edit this file to add or remove work.

Structure::

    TRACKS -> ordered dict of track_id -> {
        name, goal, cadence, topics: [
            { id, name, priority, teleprompter, template, items: [ {id, title, url, tag} ] }
        ]
    }

Item ids are stable strings ("coding.sliding_window.2"); progress.json keys on them.
"""

from __future__ import annotations

LC = "https://leetcode.com/problems/"


def _items(topic_id: str, track: str, rows: list[tuple[str, str, str]]) -> list[dict]:
    return [
        {"id": f"{track}.{topic_id}.{i + 1}", "title": title, "url": url, "tag": tag}
        for i, (title, url, tag) in enumerate(rows)
    ]


def _checks(topic_id: str, track: str, rows: list[str]) -> list[dict]:
    return [
        {"id": f"{track}.{topic_id}.{i + 1}", "title": title, "url": "", "tag": ""}
        for i, title in enumerate(rows)
    ]


# ---------------------------------------------------------------------------
# 1. CODING PATTERNS  (3 problems per pattern = done)
# ---------------------------------------------------------------------------
_CODING = [
    {
        "id": "arrays_hashing",
        "name": "Arrays & Hashing",
        "priority": "high",
        "teleprompter": (
            "When I need O(1) lookups, counts, or grouping, I reach for a hashmap or set. "
            "The trade is memory for time: one pass to build the map, one pass to answer.\n\n"
            "For grouping problems I pick a canonical key (sorted string, tuple of counts). "
            "For top-K frequency I bucket by count so it stays O(n) instead of O(n log n)."
        ),
        "template": (
            "seen = {}                      # value -> index\n"
            "for i, x in enumerate(nums):   # single pass\n"
            "    if target - x in seen:     # complement already seen?\n"
            "        return [seen[target - x], i]\n"
            "    seen[x] = i                # remember this value"
        ),
        "problems": [
            ("Two Sum", LC + "two-sum/", "easy"),
            ("Group Anagrams", LC + "group-anagrams/", "medium"),
            ("Top K Frequent Elements", LC + "top-k-frequent-elements/", "medium"),
        ],
    },
    {
        "id": "two_pointers",
        "name": "Two Pointers",
        "priority": "high",
        "teleprompter": (
            "Sorted input or a symmetric check is my cue for two pointers. I place pointers at both "
            "ends and move the one that can only improve the answer, which makes it O(n).\n\n"
            "For 3Sum I fix one element, then run two pointers on the rest, skipping duplicates "
            "so I never emit the same triple twice."
        ),
        "template": (
            "l, r = 0, len(nums) - 1        # opposite ends\n"
            "while l < r:\n"
            "    s = nums[l] + nums[r]\n"
            "    if s == target: return [l, r]\n"
            "    if s < target: l += 1      # need bigger -> move left up\n"
            "    else: r -= 1               # need smaller -> move right down"
        ),
        "problems": [
            ("Valid Palindrome", LC + "valid-palindrome/", "easy"),
            ("3Sum", LC + "3sum/", "medium"),
            ("Container With Most Water", LC + "container-with-most-water/", "medium"),
        ],
    },
    {
        "id": "sliding_window",
        "name": "Sliding Window",
        "priority": "high",
        "teleprompter": (
            "Contiguous subarray or substring with a constraint means sliding window. I grow the "
            "right edge every step and shrink the left edge only while the window is invalid, so "
            "each index is visited at most twice.\n\n"
            "I keep the window state in a counter or set so validity checks are O(1). "
            "For minimum-window problems I record the best answer each time the window becomes valid."
        ),
        "template": (
            "l = 0; best = 0; window = set()\n"
            "for r, ch in enumerate(s):          # expand right\n"
            "    while ch in window:             # shrink until valid\n"
            "        window.remove(s[l]); l += 1\n"
            "    window.add(ch)\n"
            "    best = max(best, r - l + 1)     # record answer"
        ),
        "problems": [
            ("Best Time to Buy and Sell Stock", LC + "best-time-to-buy-and-sell-stock/", "easy"),
            ("Longest Substring Without Repeating Characters", LC + "longest-substring-without-repeating-characters/", "medium"),
            ("Minimum Window Substring", LC + "minimum-window-substring/", "hard"),
        ],
    },
    {
        "id": "stack",
        "name": "Stack / Monotonic Stack",
        "priority": "high",
        "teleprompter": (
            "Matching, nesting, or 'next greater element' questions point to a stack. "
            "For next-greater I keep a monotonic stack of indices and pop whenever the current "
            "value beats the top, resolving answers as I pop.\n\n"
            "Min Stack is the classic design question: pair each value with the running minimum so "
            "get-min is O(1) without a second scan."
        ),
        "template": (
            "stack = []; res = [0] * len(temps)\n"
            "for i, t in enumerate(temps):\n"
            "    while stack and temps[stack[-1]] < t:   # current is the answer for top\n"
            "        j = stack.pop(); res[j] = i - j\n"
            "    stack.append(i)                          # wait for a warmer day"
        ),
        "problems": [
            ("Valid Parentheses", LC + "valid-parentheses/", "easy"),
            ("Min Stack", LC + "min-stack/", "medium"),
            ("Daily Temperatures", LC + "daily-temperatures/", "medium"),
        ],
    },
    {
        "id": "binary_search",
        "name": "Binary Search",
        "priority": "high",
        "teleprompter": (
            "Binary search applies whenever the answer space is monotonic, not only sorted arrays. "
            "I define the predicate, keep an invariant on lo and hi, and halve until they meet.\n\n"
            "For rotated arrays I decide which half is sorted, then check if the target lives in it. "
            "For 'minimum speed / capacity' problems I binary search on the answer itself."
        ),
        "template": (
            "lo, hi = 1, max(piles)                  # answer space\n"
            "while lo < hi:\n"
            "    mid = (lo + hi) // 2\n"
            "    if feasible(mid): hi = mid          # can do it -> try smaller\n"
            "    else: lo = mid + 1                  # too slow -> go bigger\n"
            "return lo"
        ),
        "problems": [
            ("Binary Search", LC + "binary-search/", "easy"),
            ("Search in Rotated Sorted Array", LC + "search-in-rotated-sorted-array/", "medium"),
            ("Koko Eating Bananas", LC + "koko-eating-bananas/", "medium"),
        ],
    },
    {
        "id": "linked_list",
        "name": "Linked List",
        "priority": "medium",
        "teleprompter": (
            "Linked list questions are about pointer discipline: I always keep prev, curr, next "
            "and use a dummy head to avoid edge cases at the front.\n\n"
            "LRU Cache combines a hashmap with a doubly linked list so both get and put are O(1). "
            "That is the design question interviewers use to check if I can compose structures."
        ),
        "template": (
            "prev, curr = None, head\n"
            "while curr:\n"
            "    nxt = curr.next          # save before breaking link\n"
            "    curr.next = prev         # reverse pointer\n"
            "    prev, curr = curr, nxt   # advance\n"
            "return prev"
        ),
        "problems": [
            ("Reverse Linked List", LC + "reverse-linked-list/", "easy"),
            ("Merge Two Sorted Lists", LC + "merge-two-sorted-lists/", "easy"),
            ("LRU Cache", LC + "lru-cache/", "medium"),
        ],
    },
    {
        "id": "trees",
        "name": "Trees & BST",
        "priority": "high",
        "teleprompter": (
            "Trees are recursion with a base case at null. I decide whether the answer is built "
            "bottom-up (return a value from children) or top-down (pass a bound into children).\n\n"
            "Level order uses a BFS queue. Validating a BST passes a (low, high) range down, "
            "which is the top-down pattern."
        ),
        "template": (
            "def valid(node, lo, hi):\n"
            "    if not node: return True                       # empty is valid\n"
            "    if not (lo < node.val < hi): return False      # violates range\n"
            "    return valid(node.left, lo, node.val) and valid(node.right, node.val, hi)"
        ),
        "problems": [
            ("Invert Binary Tree", LC + "invert-binary-tree/", "easy"),
            ("Binary Tree Level Order Traversal", LC + "binary-tree-level-order-traversal/", "medium"),
            ("Validate Binary Search Tree", LC + "validate-binary-search-tree/", "medium"),
        ],
    },
    {
        "id": "heap",
        "name": "Heap / Priority Queue",
        "priority": "high",
        "teleprompter": (
            "Any time I need the K best of a stream, I use a heap of size K: O(n log k) instead of "
            "sorting. Python's heapq is a min-heap, so for max behavior I push negatives.\n\n"
            "Median of a stream is two heaps: a max-heap for the lower half and a min-heap for the "
            "upper half, rebalanced so sizes differ by at most one."
        ),
        "template": (
            "import heapq\n"
            "heap = []\n"
            "for x in nums:\n"
            "    heapq.heappush(heap, x)         # push\n"
            "    if len(heap) > k: heapq.heappop(heap)   # keep only k largest\n"
            "return heap[0]                      # kth largest"
        ),
        "problems": [
            ("Kth Largest Element in a Stream", LC + "kth-largest-element-in-a-stream/", "easy"),
            ("K Closest Points to Origin", LC + "k-closest-points-to-origin/", "medium"),
            ("Find Median from Data Stream", LC + "find-median-from-data-stream/", "hard"),
        ],
    },
    {
        "id": "backtracking",
        "name": "Backtracking",
        "priority": "medium",
        "teleprompter": (
            "Enumerate all combinations, subsets, or paths means backtracking: choose, recurse, "
            "un-choose. I pass a start index to avoid duplicates and prune when a partial "
            "solution can no longer succeed.\n\n"
            "Complexity is exponential by nature, so I state it honestly and focus on pruning."
        ),
        "template": (
            "def bt(start, path):\n"
            "    res.append(path[:])              # every path is a subset\n"
            "    for i in range(start, len(nums)):\n"
            "        path.append(nums[i])         # choose\n"
            "        bt(i + 1, path)              # explore\n"
            "        path.pop()                   # un-choose"
        ),
        "problems": [
            ("Subsets", LC + "subsets/", "medium"),
            ("Combination Sum", LC + "combination-sum/", "medium"),
            ("Word Search", LC + "word-search/", "medium"),
        ],
    },
    {
        "id": "graphs",
        "name": "Graphs (BFS / DFS / Topo)",
        "priority": "high",
        "teleprompter": (
            "Grids and adjacency lists are graphs. BFS gives shortest path in unweighted graphs, "
            "DFS is simpler for connectivity, and a visited set prevents cycles.\n\n"
            "Course Schedule is cycle detection or topological sort with Kahn's algorithm: "
            "track in-degrees, peel off zero-degree nodes, and if anything remains there is a cycle."
        ),
        "template": (
            "from collections import deque\n"
            "indeg = [0]*n; adj = [[] for _ in range(n)]\n"
            "for a, b in prereqs: adj[b].append(a); indeg[a] += 1\n"
            "q = deque(i for i in range(n) if indeg[i] == 0)\n"
            "seen = 0\n"
            "while q:\n"
            "    u = q.popleft(); seen += 1\n"
            "    for v in adj[u]:\n"
            "        indeg[v] -= 1\n"
            "        if indeg[v] == 0: q.append(v)\n"
            "return seen == n                      # all nodes ordered -> no cycle"
        ),
        "problems": [
            ("Number of Islands", LC + "number-of-islands/", "medium"),
            ("Clone Graph", LC + "clone-graph/", "medium"),
            ("Course Schedule", LC + "course-schedule/", "medium"),
        ],
    },
    {
        "id": "advanced_graphs",
        "name": "Advanced Graphs (Dijkstra / MST)",
        "priority": "medium",
        "teleprompter": (
            "Weighted shortest path is Dijkstra with a min-heap keyed on distance. I skip stale "
            "entries when I pop a node already finalized.\n\n"
            "Minimum spanning tree is Prim's with a heap, or Kruskal's with union-find. "
            "Alien Dictionary is topo sort over character constraints."
        ),
        "template": (
            "dist = {src: 0}; heap = [(0, src)]\n"
            "while heap:\n"
            "    d, u = heapq.heappop(heap)\n"
            "    if d > dist.get(u, inf): continue    # stale entry\n"
            "    for v, w in adj[u]:\n"
            "        if d + w < dist.get(v, inf):\n"
            "            dist[v] = d + w; heapq.heappush(heap, (d + w, v))"
        ),
        "problems": [
            ("Network Delay Time", LC + "network-delay-time/", "medium"),
            ("Min Cost to Connect All Points", LC + "min-cost-to-connect-all-points/", "medium"),
            ("Alien Dictionary", LC + "alien-dictionary/", "hard"),
        ],
    },
    {
        "id": "dp_1d",
        "name": "1-D Dynamic Programming",
        "priority": "high",
        "teleprompter": (
            "I look for overlapping subproblems and an optimal substructure. I define dp[i] in one "
            "sentence, write the recurrence, then decide if I only need the last two values.\n\n"
            "House Robber: dp[i] = max(dp[i-1], dp[i-2] + nums[i]). LIS is O(n^2) DP, or "
            "O(n log n) with patience sorting if asked to optimize."
        ),
        "template": (
            "prev2, prev1 = 0, 0\n"
            "for x in nums:\n"
            "    prev2, prev1 = prev1, max(prev1, prev2 + x)   # skip or rob\n"
            "return prev1"
        ),
        "problems": [
            ("Climbing Stairs", LC + "climbing-stairs/", "easy"),
            ("House Robber", LC + "house-robber/", "medium"),
            ("Longest Increasing Subsequence", LC + "longest-increasing-subsequence/", "medium"),
        ],
    },
    {
        "id": "dp_2d",
        "name": "2-D Dynamic Programming",
        "priority": "medium",
        "teleprompter": (
            "Two sequences or a grid means a 2-D table. dp[i][j] is the answer for prefixes of "
            "length i and j; I fill row by row and often compress to one row.\n\n"
            "LCS: if chars match take diagonal plus one, else max of up and left. Edit Distance "
            "adds a third option for replace."
        ),
        "template": (
            "dp = [[0]*(n+1) for _ in range(m+1)]\n"
            "for i in range(1, m+1):\n"
            "    for j in range(1, n+1):\n"
            "        if a[i-1] == b[j-1]: dp[i][j] = dp[i-1][j-1] + 1\n"
            "        else: dp[i][j] = max(dp[i-1][j], dp[i][j-1])\n"
            "return dp[m][n]"
        ),
        "problems": [
            ("Unique Paths", LC + "unique-paths/", "medium"),
            ("Longest Common Subsequence", LC + "longest-common-subsequence/", "medium"),
            ("Edit Distance", LC + "edit-distance/", "medium"),
        ],
    },
    {
        "id": "greedy",
        "name": "Greedy",
        "priority": "medium",
        "teleprompter": (
            "Greedy works when a local choice never blocks the global optimum. I state the "
            "exchange argument in one line so the interviewer knows I am not guessing.\n\n"
            "Kadane's: reset the running sum when it goes negative. Jump Game: track the farthest "
            "reachable index. Gas Station: if total gas covers total cost, the start after the "
            "last failure is the answer."
        ),
        "template": (
            "best = cur = nums[0]\n"
            "for x in nums[1:]:\n"
            "    cur = max(x, cur + x)      # extend or restart\n"
            "    best = max(best, cur)\n"
            "return best"
        ),
        "problems": [
            ("Maximum Subarray", LC + "maximum-subarray/", "medium"),
            ("Jump Game", LC + "jump-game/", "medium"),
            ("Gas Station", LC + "gas-station/", "medium"),
        ],
    },
    {
        "id": "intervals",
        "name": "Intervals",
        "priority": "high",
        "teleprompter": (
            "Sort by start, then sweep. If the current interval starts before the last one ends, "
            "they overlap and I merge or count a conflict.\n\n"
            "Meeting Rooms II is the peak-overlap question: a min-heap of end times, or the "
            "two-pointer sweep over sorted starts and ends."
        ),
        "template": (
            "intervals.sort()\n"
            "merged = [intervals[0]]\n"
            "for s, e in intervals[1:]:\n"
            "    if s <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], e)  # overlap\n"
            "    else: merged.append([s, e])"
        ),
        "problems": [
            ("Merge Intervals", LC + "merge-intervals/", "medium"),
            ("Non-overlapping Intervals", LC + "non-overlapping-intervals/", "medium"),
            ("Meeting Rooms II", LC + "meeting-rooms-ii/", "medium"),
        ],
    },
    {
        "id": "bits",
        "name": "Bit Manipulation",
        "priority": "low",
        "teleprompter": (
            "XOR cancels pairs, n & (n-1) clears the lowest set bit, and shifts multiply or divide "
            "by two. These three tricks cover almost every bit question."
        ),
        "template": (
            "count = 0\n"
            "while n:\n"
            "    n &= n - 1     # drop lowest set bit\n"
            "    count += 1"
        ),
        "problems": [
            ("Single Number", LC + "single-number/", "easy"),
            ("Number of 1 Bits", LC + "number-of-1-bits/", "easy"),
            ("Counting Bits", LC + "counting-bits/", "easy"),
        ],
    },
    {
        "id": "matrix",
        "name": "Math & Matrix",
        "priority": "low",
        "teleprompter": (
            "Matrix rotation is transpose then reverse rows. Spiral traversal keeps four shrinking "
            "bounds. Set Matrix Zeroes uses the first row and column as markers to stay O(1) space."
        ),
        "template": (
            "for i in range(n):\n"
            "    for j in range(i+1, n):\n"
            "        m[i][j], m[j][i] = m[j][i], m[i][j]   # transpose\n"
            "for row in m: row.reverse()                     # mirror"
        ),
        "problems": [
            ("Rotate Image", LC + "rotate-image/", "medium"),
            ("Spiral Matrix", LC + "spiral-matrix/", "medium"),
            ("Set Matrix Zeroes", LC + "set-matrix-zeroes/", "medium"),
        ],
    },
]

for _t in _CODING:
    _t["items"] = _items(_t["id"], "coding", _t.pop("problems"))


# ---------------------------------------------------------------------------
# 2. PYTHON FLUENCY  (the 8 modules in your course, each with a prove-it task)
# ---------------------------------------------------------------------------
_PYTHON = [
    {
        "id": "sorting",
        "name": "Sorting",
        "priority": "high",
        "teleprompter": (
            "sorted() returns a new list, list.sort() is in place. Both are stable Timsort, "
            "O(n log n). I sort by key functions and tuples, never with cmp."
        ),
        "template": (
            "people.sort(key=lambda p: (-p.score, p.name))   # desc score, asc name\n"
            "from functools import cmp_to_key                 # only if truly needed"
        ),
        "checks": [
            "Sort a list of dicts by two keys (one descending) using a tuple key",
            "Explain stability and why (-score, name) works without cmp_to_key",
            "Write the sort key for 'Largest Number' (custom string ordering)",
        ],
    },
    {
        "id": "pythonic",
        "name": "Pythonic Code",
        "priority": "high",
        "teleprompter": (
            "Comprehensions, enumerate, zip, unpacking, and generators make code read like the "
            "algorithm. I use them to keep interview code short and obviously correct."
        ),
        "template": (
            "pairs = {a: b for a, b in zip(keys, vals)}\n"
            "total = sum(x for x in nums if x > 0)   # generator, no temp list\n"
            "first, *rest = items"
        ),
        "checks": [
            "Rewrite a nested loop as a comprehension with a condition",
            "Use enumerate + zip + unpacking in one function without indexes",
            "Write a generator that yields chunks of size k from an iterable",
        ],
    },
    {
        "id": "lists",
        "name": "Lists",
        "priority": "medium",
        "teleprompter": (
            "Append and pop from the end are O(1); insert and pop from the front are O(n). "
            "Slicing copies. I know these costs so I pick deque when I need both ends."
        ),
        "template": (
            "nums[::-1]          # reversed copy\n"
            "nums[i:j]           # slice copy, O(j-i)\n"
            "[0] * n             # preallocate"
        ),
        "checks": [
            "State Big-O of append, pop(), pop(0), insert(0), 'in', slicing",
            "Explain the [[0]*n]*m aliasing bug and the correct 2-D init",
            "Implement in-place removal of duplicates from a sorted list",
        ],
    },
    {
        "id": "stacks_queues",
        "name": "Stacks and Queues",
        "priority": "high",
        "teleprompter": (
            "A list is a stack. collections.deque is the queue: O(1) popleft. "
            "I never use list.pop(0) in a BFS."
        ),
        "template": (
            "from collections import deque\n"
            "q = deque([start]); q.append(x); q.popleft()\n"
            "stack = []; stack.append(x); stack.pop()"
        ),
        "checks": [
            "Implement a queue using two stacks with amortized O(1)",
            "Write BFS with deque and explain why pop(0) is wrong",
            "Implement a monotonic deque for sliding window maximum",
        ],
    },
    {
        "id": "lists_2d",
        "name": "2-D Lists",
        "priority": "medium",
        "teleprompter": (
            "Grids are lists of lists. I keep a DIRS tuple for neighbors and a bounds check "
            "helper so DFS on grids is three lines."
        ),
        "template": (
            "DIRS = ((1,0),(-1,0),(0,1),(0,-1))\n"
            "def inb(r, c): return 0 <= r < R and 0 <= c < C\n"
            "grid = [[0]*C for _ in range(R)]"
        ),
        "checks": [
            "Write grid DFS with a bounds helper and visited marking in place",
            "Transpose and rotate a matrix without numpy",
            "Iterate a matrix diagonally",
        ],
    },
    {
        "id": "hashmaps",
        "name": "Hashmaps and Hashsets",
        "priority": "high",
        "teleprompter": (
            "dict and set are O(1) average. defaultdict removes key checks, Counter gives counts "
            "and most_common. Keys must be hashable, so lists become tuples."
        ),
        "template": (
            "from collections import defaultdict, Counter\n"
            "groups = defaultdict(list); groups[key].append(x)\n"
            "Counter(s).most_common(k)"
        ),
        "checks": [
            "Use defaultdict(list) to group anagrams with a tuple key",
            "Explain hashability: why tuple works as a key and list does not",
            "Implement a frequency counter without Counter, then with it",
        ],
    },
    {
        "id": "heaps",
        "name": "Heaps / Priority Queues",
        "priority": "high",
        "teleprompter": (
            "heapq is a min-heap on a list. heapify is O(n); push and pop are O(log n). "
            "For max-heap I negate; for objects I push (key, tiebreak, obj) tuples."
        ),
        "template": (
            "import heapq\n"
            "heapq.heapify(nums)\n"
            "heapq.heappush(h, (-dist, i, item))   # max-heap via negation\n"
            "heapq.nlargest(k, nums)"
        ),
        "checks": [
            "Implement top-K with a size-K min-heap and explain O(n log k)",
            "Use tuple tiebreakers so unorderable objects never get compared",
            "Merge k sorted lists with a heap",
        ],
    },
    {
        "id": "sorted_containers",
        "name": "Sorted Dicts and Sorted Sets",
        "priority": "medium",
        "teleprompter": (
            "Python has no built-in balanced BST. In interviews I use bisect on a sorted list "
            "for O(log n) search with O(n) insert, or say I'd use sortedcontainers.SortedList."
        ),
        "template": (
            "import bisect\n"
            "i = bisect.bisect_left(arr, x)     # insertion point\n"
            "bisect.insort(arr, x)              # O(n) insert keeps sorted"
        ),
        "checks": [
            "Use bisect to implement floor/ceiling lookup in a sorted list",
            "Explain when SortedList beats a heap (need ordered iteration + removal)",
            "Implement 'My Calendar I' with bisect",
        ],
    },
]

for _t in _PYTHON:
    _t["items"] = _checks(_t["id"], "python", _t.pop("checks"))


# ---------------------------------------------------------------------------
# 3. OOP  (the 6 modules in your course)
# ---------------------------------------------------------------------------
_OOP = [
    {
        "id": "classes_objects",
        "name": "Classes and Objects",
        "priority": "medium",
        "teleprompter": (
            "A class is the blueprint, an object is the instance. __init__ sets instance state, "
            "self is the instance, and dunder methods (__repr__, __eq__, __lt__) integrate with "
            "Python's protocols."
        ),
        "template": (
            "class Order:\n"
            "    def __init__(self, oid, qty): self.oid, self.qty = oid, qty\n"
            "    def __repr__(self): return f'Order({self.oid}, {self.qty})'\n"
            "    def __eq__(self, o): return self.oid == o.oid"
        ),
        "checks": [
            "Implement a class with __init__, __repr__, __eq__ and __hash__",
            "Explain the difference between __str__ and __repr__",
            "Use @dataclass and explain what it generates",
        ],
    },
    {
        "id": "encapsulation",
        "name": "Encapsulation",
        "priority": "medium",
        "teleprompter": (
            "Python encapsulates by convention: _protected and __private (name-mangled). "
            "@property gives controlled access without breaking callers."
        ),
        "template": (
            "class Account:\n"
            "    def __init__(self): self._balance = 0\n"
            "    @property\n"
            "    def balance(self): return self._balance\n"
            "    @balance.setter\n"
            "    def balance(self, v):\n"
            "        if v < 0: raise ValueError\n"
            "        self._balance = v"
        ),
        "checks": [
            "Implement a validated @property setter",
            "Explain name mangling for __attr and when to use it",
            "Refactor a class with public attributes to encapsulated ones",
        ],
    },
    {
        "id": "class_attributes",
        "name": "Class Attributes",
        "priority": "low",
        "teleprompter": (
            "Class attributes are shared across instances; instance attributes shadow them. "
            "@classmethod gets cls (alternate constructors), @staticmethod gets nothing."
        ),
        "template": (
            "class Config:\n"
            "    instances = 0                      # shared\n"
            "    @classmethod\n"
            "    def from_env(cls): return cls()    # alternate constructor\n"
            "    @staticmethod\n"
            "    def validate(v): return v > 0"
        ),
        "checks": [
            "Show the mutable class attribute bug (shared list) and the fix",
            "Write a @classmethod alternate constructor",
            "Explain when @staticmethod is preferable to a module function",
        ],
    },
    {
        "id": "inheritance",
        "name": "Inheritance",
        "priority": "medium",
        "teleprompter": (
            "Subclasses extend or override; super() delegates up the MRO. I prefer composition "
            "over deep hierarchies and keep inheritance for true is-a relationships."
        ),
        "template": (
            "class Animal:\n"
            "    def __init__(self, name): self.name = name\n"
            "class Dog(Animal):\n"
            "    def __init__(self, name, breed):\n"
            "        super().__init__(name); self.breed = breed"
        ),
        "checks": [
            "Use super() correctly in a subclass __init__",
            "Explain MRO with a diamond and print Cls.__mro__",
            "Refactor an inheritance chain to composition and justify it",
        ],
    },
    {
        "id": "polymorphism",
        "name": "Polymorphism",
        "priority": "high",
        "teleprompter": (
            "Same interface, different behavior. Python is duck-typed, so any object with the "
            "method works; I use it to swap strategies without if-chains."
        ),
        "template": (
            "class Circle:\n"
            "    def area(self): return 3.14159 * self.r ** 2\n"
            "class Square:\n"
            "    def area(self): return self.s ** 2\n"
            "total = sum(shape.area() for shape in shapes)   # no isinstance"
        ),
        "checks": [
            "Implement Area Calculator (course exercise 31) with duck typing",
            "Implement Polymorphic Battle System (course exercise 30)",
            "Replace an isinstance if-chain with method overriding",
        ],
    },
    {
        "id": "abstraction",
        "name": "Abstraction",
        "priority": "high",
        "teleprompter": (
            "ABCs define the contract; Protocols define it structurally. I use ABC when I own "
            "the hierarchy and Protocol when I want to type third-party objects."
        ),
        "template": (
            "from abc import ABC, abstractmethod\n"
            "class Notifier(ABC):\n"
            "    @abstractmethod\n"
            "    def send(self, msg: str) -> None: ...\n"
            "class Telegram(Notifier):\n"
            "    def send(self, msg): print('tg', msg)"
        ),
        "checks": [
            "Define an ABC with an abstract method and a concrete subclass",
            "Define a typing.Protocol and show structural typing",
            "Explain ABC vs Protocol trade-offs in one minute",
        ],
    },
]

for _t in _OOP:
    _t["items"] = _checks(_t["id"], "oop", _t.pop("checks"))


# ---------------------------------------------------------------------------
# 4. DESIGN PATTERNS  (the 10 in your course)
# ---------------------------------------------------------------------------
_PATTERNS = [
    {
        "id": "factory",
        "name": "Factory Method",
        "priority": "high",
        "teleprompter": (
            "Factory Method moves object creation behind one function so callers never name a "
            "concrete class. I use it when the type depends on config or input, such as picking "
            "a notifier for Telegram versus email."
        ),
        "template": (
            "class NotifierFactory:\n"
            "    _registry = {'telegram': Telegram, 'email': Email}\n"
            "    @classmethod\n"
            "    def create(cls, kind, **kw):\n"
            "        return cls._registry[kind](**kw)   # caller never imports Telegram"
        ),
        "checks": [
            "Implement a registry-based factory in Python",
            "Explain when Factory beats a plain if/else and when it is overkill",
            "Name one real use from your work (notifier, parser, broker adapter)",
        ],
    },
    {
        "id": "singleton",
        "name": "Singleton",
        "priority": "medium",
        "teleprompter": (
            "Singleton guarantees one instance, typically for config or a connection pool. "
            "In Python a module-level instance is usually enough; I mention the thread-safety "
            "and testability downsides so the interviewer knows I would not overuse it."
        ),
        "template": (
            "class Settings:\n"
            "    _instance = None\n"
            "    def __new__(cls):\n"
            "        if cls._instance is None:\n"
            "            cls._instance = super().__new__(cls)\n"
            "        return cls._instance"
        ),
        "checks": [
            "Implement Singleton via __new__ and via a module-level instance",
            "Explain why Singleton hurts testing and how DI fixes it",
            "Make it thread-safe with a lock",
        ],
    },
    {
        "id": "builder",
        "name": "Builder",
        "priority": "medium",
        "teleprompter": (
            "Builder assembles a complex object step by step with a fluent interface, so I avoid "
            "constructors with ten optional parameters. It reads well for queries, requests, and "
            "config objects."
        ),
        "template": (
            "class QueryBuilder:\n"
            "    def __init__(self): self._parts = []\n"
            "    def where(self, c): self._parts.append(f'WHERE {c}'); return self\n"
            "    def limit(self, n): self._parts.append(f'LIMIT {n}'); return self\n"
            "    def build(self): return ' '.join(self._parts)"
        ),
        "checks": [
            "Implement a fluent builder that returns self",
            "Contrast Builder with dataclass defaults and kwargs in Python",
            "Explain director vs builder roles in one sentence",
        ],
    },
    {
        "id": "prototype",
        "name": "Prototype",
        "priority": "low",
        "teleprompter": (
            "Prototype clones an existing object instead of constructing from scratch. "
            "In Python that is copy.deepcopy or a clone method; useful for templates and "
            "default configurations."
        ),
        "template": (
            "import copy\n"
            "class Campaign:\n"
            "    def clone(self, **overrides):\n"
            "        c = copy.deepcopy(self)\n"
            "        c.__dict__.update(overrides)\n"
            "        return c"
        ),
        "checks": [
            "Implement clone() with deepcopy and overrides",
            "Explain shallow vs deep copy pitfalls with nested lists",
            "Name a use case (template objects, snapshot state)",
        ],
    },
    {
        "id": "adapter",
        "name": "Adapter",
        "priority": "high",
        "teleprompter": (
            "Adapter wraps an incompatible interface so existing code can use it unchanged. "
            "I used this shape wrapping broker APIs and payment processors behind one interface."
        ),
        "template": (
            "class AlpacaAdapter(Broker):\n"
            "    def __init__(self, client): self._c = client\n"
            "    def buy(self, sym, qty):\n"
            "        return self._c.submit_order(symbol=sym, qty=qty, side='buy')"
        ),
        "checks": [
            "Implement an adapter over a third-party client to a local interface",
            "Explain Adapter vs Facade vs Decorator in three sentences",
            "Show how the adapter makes the third-party client mockable in tests",
        ],
    },
    {
        "id": "decorator",
        "name": "Decorator",
        "priority": "high",
        "teleprompter": (
            "Decorator adds behavior around an object or function without changing it: "
            "retries, caching, logging, auth. Python's @decorator syntax is the same idea "
            "applied to functions."
        ),
        "template": (
            "import functools, time\n"
            "def retry(times=3):\n"
            "    def deco(fn):\n"
            "        @functools.wraps(fn)\n"
            "        def wrapper(*a, **kw):\n"
            "            for i in range(times):\n"
            "                try: return fn(*a, **kw)\n"
            "                except Exception:\n"
            "                    if i == times - 1: raise\n"
            "                    time.sleep(2 ** i)       # exponential backoff\n"
            "        return wrapper\n"
            "    return deco"
        ),
        "checks": [
            "Write a parameterized retry decorator with functools.wraps",
            "Implement the class-based Decorator pattern (wrapping an object)",
            "Explain why wraps matters for introspection and debugging",
        ],
    },
    {
        "id": "facade",
        "name": "Facade",
        "priority": "medium",
        "teleprompter": (
            "Facade gives a simple entry point over a complex subsystem. It is how I keep "
            "callers away from the details of a multi-step workflow like 'place trade' that "
            "touches risk, broker, and journal."
        ),
        "template": (
            "class TradeFacade:\n"
            "    def place(self, sym, qty):\n"
            "        self.risk.check(sym, qty)\n"
            "        oid = self.broker.buy(sym, qty)\n"
            "        self.journal.record(oid)\n"
            "        return oid"
        ),
        "checks": [
            "Implement a facade over three collaborating services",
            "Explain the difference between Facade and a god object",
            "Show how the facade simplifies testing of callers",
        ],
    },
    {
        "id": "strategy",
        "name": "Strategy",
        "priority": "high",
        "teleprompter": (
            "Strategy makes an algorithm pluggable: define an interface, implement variants, "
            "inject the one you want. It replaces if-chains and is the pattern behind pricing "
            "rules, routing logic, and scoring engines."
        ),
        "template": (
            "class Routing(Protocol):\n"
            "    def pick(self, txn) -> str: ...\n"
            "class ByMerchantCode:\n"
            "    def pick(self, txn): return 'network_a' if txn.mcc < 5000 else 'network_b'\n"
            "class Authorizer:\n"
            "    def __init__(self, routing: Routing): self.routing = routing"
        ),
        "checks": [
            "Implement Strategy with a Protocol and two variants",
            "Explain Strategy vs State: same shape, different intent",
            "Map it to a real system you built (auth routing, rule engine)",
        ],
    },
    {
        "id": "observer",
        "name": "Observer",
        "priority": "high",
        "teleprompter": (
            "Observer lets subscribers react to events without the publisher knowing them. "
            "It is the in-process version of pub/sub; Kafka is the distributed version."
        ),
        "template": (
            "class Signal:\n"
            "    def __init__(self): self._subs = []\n"
            "    def subscribe(self, fn): self._subs.append(fn)\n"
            "    def emit(self, evt):\n"
            "        for fn in self._subs: fn(evt)   # fan out"
        ),
        "checks": [
            "Implement subscribe/emit with unsubscribe support",
            "Explain memory leak risk and how weakref helps",
            "Compare in-process Observer to Kafka pub/sub trade-offs",
        ],
    },
    {
        "id": "state",
        "name": "State",
        "priority": "medium",
        "teleprompter": (
            "State moves each state's behavior into its own class and lets the context "
            "delegate. It cleans up order lifecycles and connection state machines where "
            "transitions would otherwise be a tangle of conditionals."
        ),
        "template": (
            "class Pending:\n"
            "    def next(self, order): order.state = Filled()\n"
            "class Filled:\n"
            "    def next(self, order): raise ValueError('terminal')\n"
            "class Order:\n"
            "    def __init__(self): self.state = Pending()\n"
            "    def advance(self): self.state.next(self)"
        ),
        "checks": [
            "Implement a 3-state order lifecycle with State classes",
            "Explain when an enum + dict transition table is enough instead",
            "Draw the transitions and name the invalid ones",
        ],
    },
]

for _t in _PATTERNS:
    _t["items"] = _checks(_t["id"], "design_patterns", _t.pop("checks"))


# ---------------------------------------------------------------------------
# 5. SYSTEM DESIGN  (your 5-step template applied to 10 systems)
# ---------------------------------------------------------------------------
SD_STEPS = [
    "Requirements: functional, non-functional, clarifying questions, out of scope",
    "Design: API specs + functional architecture diagram",
    "Scale & reliability: NFR diagram (caching, sharding, replication, queues)",
    "Trade-offs: 3 decisions with alternatives and why",
    "Teleprompter: 3-paragraph walkthrough rehearsed out loud",
]


def _sd(topic_id: str, name: str, priority: str, teleprompter: str, key_points: str) -> dict:
    return {
        "id": topic_id,
        "name": name,
        "priority": priority,
        "teleprompter": teleprompter,
        "template": key_points,
        "items": _checks(topic_id, "system_design", SD_STEPS),
    }


_SYSTEM_DESIGN = [
    _sd(
        "rate_limiter", "Rate Limiter", "high",
        "I start by asking scope: per user, per API key, or global, and whether limits must be "
        "exact or approximate. Core algorithm is token bucket or sliding window log in Redis, "
        "keyed by client id, with atomic Lua scripts for check-and-decrement.\n\n"
        "For scale I put it at the gateway, shard Redis by client id, and fail open or closed "
        "based on the product's risk appetite. Trade-off: fixed window is cheap but bursty at "
        "boundaries; sliding log is exact but memory-heavy; sliding counter is the middle ground.",
        "Token bucket vs sliding window; Redis Lua atomicity; fail-open vs fail-closed; "
        "429 + Retry-After headers; distributed clock skew",
    ),
    _sd(
        "url_shortener", "URL Shortener / Key-Value Service", "medium",
        "Functional: create short code, redirect, optional expiry and analytics. Non-functional: "
        "read-heavy at 100:1, low latency, high availability. I generate keys with a pre-allocated "
        "key range service or base62 of a snowflake id to avoid collisions.\n\n"
        "Reads hit a cache in front of a KV store; writes are rare. 301 vs 302 decides whether "
        "the browser caches the redirect and whether I still get analytics.",
        "Base62 encoding; key generation service vs hash; 301 vs 302; cache-aside; "
        "analytics via async event stream",
    ),
    _sd(
        "news_feed", "News Feed / Timeline", "high",
        "Requirements: publish post, fetch feed, follow graph, ranked or chronological. "
        "The core decision is fan-out on write (push to followers' feed caches) versus fan-out "
        "on read (merge at request time). I do hybrid: push for normal users, pull for celebrities.\n\n"
        "Feed cache in Redis lists per user, posts in a sharded store, ranking service reads "
        "candidates and scores them. Media goes to object storage plus CDN.",
        "Fan-out write vs read; hybrid for celebrities; Redis feed cache; ranking as a "
        "separate service; pagination via cursor",
    ),
    _sd(
        "chat", "Chat System (WhatsApp / Slack)", "high",
        "Functional: 1:1 and group messages, delivery and read receipts, online presence, "
        "message history. Non-functional: low latency, ordering per conversation, at-least-once "
        "delivery with dedup.\n\n"
        "Clients hold WebSocket connections to chat servers; a service discovery layer maps user "
        "to server. Messages are persisted to a wide-column store keyed by conversation id and "
        "time, and delivered via a message queue to the recipient's server. Presence uses "
        "heartbeats with TTL in a KV store.",
        "WebSocket + connection registry; message id ordering; Cassandra partition by "
        "conversation; presence heartbeats; push notifications for offline",
    ),
    _sd(
        "notification", "Notification System", "high",
        "This maps directly to my Telegram and webhook work. Requirements: multi-channel "
        "(push, SMS, email, chat), templating, priority, rate limiting per user, dedup. "
        "Producers publish events to a queue; workers per channel render and send.\n\n"
        "Reliability comes from retries with exponential backoff, dead letter queues, and "
        "idempotency keys so a retried event never double-sends. I track delivery rate and "
        "provider availability per channel.",
        "Queue per channel; idempotency key; retry + DLQ; user preferences and quiet hours; "
        "provider failover",
    ),
    _sd(
        "ad_click_aggregation", "Ad Click Aggregation / Real-time Analytics", "high",
        "This is my Apple domain. Requirements: ingest click events at high volume, aggregate "
        "clicks per ad per minute, top-N ads, exactly-once counts for billing. Events flow "
        "through Kafka into a stream processor (Flink or Spark Structured Streaming) that "
        "windows and aggregates.\n\n"
        "Results land in an OLAP store for queries and raw events in a data lake for "
        "reconciliation. Exactly-once comes from Kafka transactions plus idempotent sinks; "
        "late events are handled with watermarks and a reconciliation batch job.",
        "Kafka partitions by ad id; tumbling windows + watermarks; exactly-once via "
        "transactional sink; lambda vs kappa; reconciliation job",
    ),
    _sd(
        "payment", "Payment / Authorization System", "high",
        "Requirements: authorize, capture, refund; idempotent; consistent ledger; PCI scope "
        "minimized via tokenization. I separate the payment service, ledger, and PSP adapters.\n\n"
        "Every request carries an idempotency key stored with the response. The ledger is "
        "append-only double-entry. Reconciliation with the PSP runs nightly. Failure handling "
        "uses a state machine per payment and a retry queue with DLQ.",
        "Idempotency keys; double-entry ledger; tokenization / FPE; state machine; "
        "PSP adapter pattern; reconciliation",
    ),
    _sd(
        "distributed_cache", "Distributed Cache / Key-Value Store", "medium",
        "Requirements: get/put with TTL, high availability, horizontal scale. Data is "
        "partitioned by consistent hashing with virtual nodes; each partition is replicated "
        "to N nodes with quorum reads and writes.\n\n"
        "I discuss eviction (LRU per node), hot key mitigation (local cache, key splitting), "
        "and consistency trade-offs (eventual with vector clocks or last-write-wins).",
        "Consistent hashing + vnodes; replication and quorum; LRU eviction; hot keys; "
        "cache stampede protection",
    ),
    _sd(
        "ml_serving", "ML Model Serving / Feature Store", "high",
        "Requirements: register model versions, serve predictions at low latency, A/B and "
        "canary rollouts, feature freshness. This is my model catalog work. A registry stores "
        "artifacts and metadata; a deployment controller (Kubernetes operator) reconciles "
        "desired versions into serving pods.\n\n"
        "Online features come from a low-latency store populated by streaming jobs, offline "
        "features from the warehouse with point-in-time correctness. I monitor latency, GPU "
        "utilization, and prediction drift.",
        "Model registry; operator reconciliation; online vs offline store; canary via "
        "traffic split; drift monitoring; batching and quantization",
    ),
    _sd(
        "autocomplete", "Search Autocomplete / Typeahead", "medium",
        "Requirements: prefix suggestions in under 100 ms, top-K by popularity, updated "
        "hourly or daily. A trie with top-K cached at each node serves reads; a batch "
        "pipeline rebuilds it from query logs.\n\n"
        "Tries are sharded by prefix, replicated, and served from memory behind a CDN or "
        "edge cache for the hottest prefixes.",
        "Trie with cached top-K; shard by prefix; batch rebuild from logs; browser "
        "debouncing; edge caching",
    ),
]


# ---------------------------------------------------------------------------
# 6. BEHAVIORAL  (STAR stories, one per leadership signal)
# ---------------------------------------------------------------------------
STAR_STEPS = [
    "Write the STAR story (S/T one sentence each, A three bullets, R with a metric)",
    "Rehearse out loud under 2 minutes and record yourself",
    "Prepare the two most likely follow-ups and answers",
]


def _bq(topic_id: str, name: str, priority: str, question: str, story_hint: str) -> dict:
    return {
        "id": topic_id,
        "name": name,
        "priority": priority,
        "teleprompter": question,
        "template": story_hint,
        "items": _checks(topic_id, "behavioral", STAR_STEPS),
    }


_BEHAVIORAL = [
    _bq("lead_ambiguity", "Leading through ambiguity", "high",
        "Tell me about a time you led a project with unclear requirements.",
        "Apple: batch to real-time streaming migration. Started with no agreed SLA; drove "
        "the definition of 'minutes not hours', aligned three teams, delivered exactly-once."),
    _bq("technical_disagreement", "Technical disagreement", "high",
        "Describe a time you disagreed with a senior engineer or manager. What happened?",
        "Marqeta: Jenkins to Drone CI. Pushed for phased POC over big-bang rewrite; used "
        "rollout duration and rollback frequency data to win the argument."),
    _bq("failure", "Failure and learning", "high",
        "Tell me about a significant mistake you made and what you learned.",
        "Pick a real incident: alert noise or a missed cooldown, a prod deploy that needed a "
        "rollback. Own it, show the postmortem action, show the metric that improved."),
    _bq("influence_without_authority", "Influence without authority", "high",
        "Give an example of getting buy-in from teams you did not manage.",
        "Apple: SpiceDB authorization adopted across teams. Built the passport cache to remove "
        "their latency objection; produced audit logs that satisfied compliance."),
    _bq("mentoring", "Mentoring and growing others", "medium",
        "How have you helped a junior engineer grow?",
        "Go SDK for Search Ads partners: paired a junior on integration and load tests; "
        "they now own the SDK release process."),
    _bq("scale_impact", "Highest-impact technical work", "high",
        "What is the most complex system you have designed? Walk me through it.",
        "Payment Authorization Service at Marqeta: routing by merchant codes, real-time balance "
        "checks, SLA tracking. Or the Model Catalog Service with the kopf operator."),
    _bq("prioritization", "Prioritization under pressure", "medium",
        "Tell me about a time you had to cut scope or say no.",
        "Visa DR system: chose active-passive over active-active to hit the deadline; "
        "documented RTO/RPO and the path to active-active."),
    _bq("cross_team_conflict", "Cross-team conflict", "medium",
        "Describe a conflict between teams and how you resolved it.",
        "Offline enrichment pipeline observability: two teams wanted different metrics "
        "platforms; solved with dual publishing to DataDog and Mosaic."),
    _bq("raising_the_bar", "Raising engineering quality", "medium",
        "How have you improved engineering practices on a team?",
        "Airflow DAG CI/CD framework with multi-system validation; Gatling performance "
        "framework that found connection-pool exhaustion before customers did."),
    _bq("why_staff", "Why Staff / why this company", "high",
        "Why do you want this role, and what does Staff mean to you?",
        "Staff = multiplying teams, owning direction across boundaries, being the person who "
        "makes the hard call with data. Tie to the target company's domain."),
]


# ---------------------------------------------------------------------------
# TRACK REGISTRY
# ---------------------------------------------------------------------------
TRACKS: dict[str, dict] = {
    "coding": {
        "name": "Coding Patterns",
        "icon": "🧩",
        "goal": "3 LeetCode problems per pattern, solved without hints, explained out loud.",
        "cadence": "1 pattern per day",
        "topics": _CODING,
    },
    "python": {
        "name": "Python Fluency",
        "icon": "🐍",
        "goal": "Every course module with its 3 prove-it checks done from memory.",
        "cadence": "1 module per day alongside coding",
        "topics": _PYTHON,
    },
    "oop": {
        "name": "OOP",
        "icon": "🏗️",
        "goal": "Six OOP pillars, each with 3 checks including the course exercises.",
        "cadence": "1 pillar per day",
        "topics": _OOP,
    },
    "design_patterns": {
        "name": "Design Patterns",
        "icon": "📐",
        "goal": "10 patterns: implement in Python, explain in 30 seconds, map to real work.",
        "cadence": "1 pattern per day",
        "topics": _PATTERNS,
    },
    "system_design": {
        "name": "System Design",
        "icon": "🗺️",
        "goal": "10 systems, each through the full 5-step template and rehearsed out loud.",
        "cadence": "1 system every 2 days",
        "topics": _SYSTEM_DESIGN,
    },
    "behavioral": {
        "name": "Behavioral (STAR)",
        "icon": "🎤",
        "goal": "10 STAR stories written, rehearsed under 2 minutes, follow-ups ready.",
        "cadence": "1 story per day",
        "topics": _BEHAVIORAL,
    },
}


def all_items() -> list[dict]:
    out = []
    for track_id, track in TRACKS.items():
        for topic in track["topics"]:
            for item in topic["items"]:
                out.append({**item, "track": track_id, "topic": topic["id"], "topic_name": topic["name"]})
    return out


def total_items() -> int:
    return len(all_items())
