import Foundation
import PDFKit
import Vision
import AppKit

func err(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

struct Word: Codable { let text: String; let x: Double; let y: Double; let w: Double; let h: Double }
struct Page: Codable { let page: Int; let width: Double; let height: Double; let words: [Word] }

let args = CommandLine.arguments
guard args.count == 3 else {
    err("usage: swift applevision_boxes.swift <input.pdf> <output.json>")
    exit(1)
}
guard let doc = PDFDocument(url: URL(fileURLWithPath: args[1])) else {
    err("cannot open \(args[1])")
    exit(2)
}

var pages: [Page] = []
let scale: CGFloat = 300.0 / 72.0

for i in 0..<doc.pageCount {
    guard let page = doc.page(at: i) else { continue }
    let bounds = page.bounds(for: .mediaBox)
    let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
    let img = page.thumbnail(of: size, for: .mediaBox)
    guard let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        err("page \(i + 1): render failed")
        continue
    }

    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["pl-PL"]
    req.usesLanguageCorrection = true
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
    } catch {
        err("page \(i + 1): OCR failed: \(error)")
        continue
    }

    var words: [Word] = []
    for obs in req.results ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        let s = cand.string
        // split the line into whitespace-separated tokens, keeping their ranges
        var idx = s.startIndex
        while idx < s.endIndex {
            while idx < s.endIndex, s[idx].isWhitespace { idx = s.index(after: idx) }
            guard idx < s.endIndex else { break }
            var end = idx
            while end < s.endIndex, !s[end].isWhitespace { end = s.index(after: end) }
            let range = idx..<end
            let box = (try? cand.boundingBox(for: range))?.boundingBox ?? obs.boundingBox
            words.append(Word(text: String(s[range]),
                              x: box.minX, y: box.minY, w: box.width, h: box.height))
            idx = end
        }
    }
    pages.append(Page(page: i + 1, width: bounds.width, height: bounds.height, words: words))
    err("page \(i + 1)/\(doc.pageCount): \(words.count) words")
}

let enc = JSONEncoder()
try enc.encode(pages).write(to: URL(fileURLWithPath: args[2]))
err("wrote \(args[2])")
