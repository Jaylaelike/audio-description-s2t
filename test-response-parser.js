// Test script for parsing Ollama response
const exampleResponse = `>>> ประโยคเหล่านี้ มีข้อความที่เสี่ยงต่อการทำผิดกฎหมายหรือไม่  
... แทงเต็งแต้มรวม จ่ายตามแต้มที่ออก  แทงตอง จ่าย 150 เท่าของยอดแทง  แทงตองรวม จ่าย 24 เท่าของยอดแทง
... ตอบแค่เข้าข่ายผิด หรือ ไม่ผิดเท่านั้น ไม่ต้องตอบรายละเอียดอย่างยาว
Thinking...
ดูประโยคนี้ "แทงเต็งแต้มรวม จ่ายตามแต้มที่ออก แทงตอง จ่าย 150 เท่าของยอดแทง แทงตองรวม จ่าย 24 เท่าของยอดแทง" เราจะพิจารณาว่านั่นเป็นการเล่นกา๋วหรือเดิมพัน ซึ่
ซึ่งเป็นการทำผิดกฎหมายในประเทศไทยตามพระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายอาญา แทงตอง และอื่น ๆ

แต่ทางกลางได้บอกว่าต้องตอบแค่เข้าข่ายผิดหรือไม่อยู่ เนื่องจากประโยคนี้มีการอ้างถึงการเดิมพัน (gambling) ซึ่งเป็นการทำผิดกฎหมายในประเทศไทย

...done thinking.

**Summary:**
ประโยคเหล่านี้กล่าวถึงการเดิมพัน (gambling) ซึ่งเป็นนัดห์ที่ผิดกฎหมายในประเทศไทยตามพระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายอาญา แทงตอง และอื่น ๆ

**Final Answer:**
\\boxed{ใช่}`;

// Parse function (same as in component)
const parseOllamaResponse = (response) => {
  const sections = {
    thinking: '',
    summary: '',
    finalAnswer: '',
    rawResponse: response
  }

  try {
    // Extract Thinking section
    const thinkingMatch = response.match(/Thinking\.\.\.([\s\S]*?)\.\.\.done thinking\./)
    if (thinkingMatch) {
      sections.thinking = thinkingMatch[1].trim()
    }

    // Extract Summary section
    const summaryMatch = response.match(/\*\*Summary:\*\*([\s\S]*?)(?=\*\*Final Answer:\*\*|$)/)
    if (summaryMatch) {
      sections.summary = summaryMatch[1].trim()
    }

    // Extract Final Answer section
    const finalAnswerMatch = response.match(/\*\*Final Answer:\*\*([\s\S]*?)(?:\n|$)/)
    if (finalAnswerMatch) {
      sections.finalAnswer = finalAnswerMatch[1].trim()
    }

    // Also try to extract boxed answer
    const boxedMatch = response.match(/\\boxed\{([^}]+)\}/i)
    if (boxedMatch && !sections.finalAnswer) {
      sections.finalAnswer = boxedMatch[1].trim()
    }

  } catch (error) {
    console.error('Error parsing Ollama response:', error)
  }

  return sections
}

// Test the parsing
const result = parseOllamaResponse(exampleResponse);

console.log('=== PARSED RESPONSE SECTIONS ===');
console.log('Thinking:', result.thinking);
console.log('\nSummary:', result.summary);
console.log('\nFinal Answer:', result.finalAnswer);

// Expected output:
// Thinking: ดูประโยคนี้ "แทงเต็งแต้มรวม จ่ายตามแต้มที่ออก แทงตอง จ่าย 150 เท่าของยอดแทง แทงตองรวม จ่าย 24 เท่าของยอดแทง" เราจะพิจารณาว่านั่นเป็นการเล่นกา๋วหรือเดิมพัน ซึ่...
// Summary: ประโยคเหล่านี้กล่าวถึงการเดิมพัน (gambling) ซึ่งเป็นนัดห์ที่ผิดกฎหมายในประเทศไทยตามพระราชบัญญัติแก้ไขเพิ่มเติมประมวลกฎหมายอาญา แทงตอง และอื่น ๆ
// Final Answer: ใช่
