// 主代码文件: src/index.ts
// 实现一个函数，接收一个字符串数组，返回按字母顺序排序后的数组，并去除重复项

export function sortAndDeduplicate(arr: string[]): string[] {
    if (!Array.isArray(arr)) {
        throw new Error('Input must be an array');
    }
    // 使用 Set 去重，然后排序
    const uniqueSorted = [...new Set(arr)].sort();
    return uniqueSorted;
}

// 如果直接运行此文件，可以测试
if (require.main === module) {
    const testArray = ['banana', 'apple', 'cherry', 'apple', 'date'];
    console.log('Original array:', testArray);
    console.log('Sorted and deduplicated:', sortAndDeduplicate(testArray));
}