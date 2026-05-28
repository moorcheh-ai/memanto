// 主代码：实现一个类型安全的挑战函数
// 该函数接收一个字符串数组，返回所有字符串的大写形式
// 如果输入为空数组，抛出错误

export function toUpperCaseArray(arr: string[]): string[] {
    if (arr.length === 0) {
        throw new Error('输入数组不能为空');
    }
    return arr.map((s) => s.toUpperCase());
}
