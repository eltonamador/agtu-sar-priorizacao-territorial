#!/usr/bin/env swift

import Foundation
import ImageIO

private let contractVersion = "IMAGEIO-WHITELIST-v1"

private func emitJSON(_ value: [String: Any], to handle: FileHandle) {
    guard JSONSerialization.isValidJSONObject(value),
          let data = try? JSONSerialization.data(
              withJSONObject: value,
              options: [.sortedKeys]
          ) else {
        let fallback = Data("{\"error_code\":\"SERIALIZATION_FAILURE\"}\n".utf8)
        handle.write(fallback)
        return
    }
    handle.write(data)
    handle.write(Data("\n".utf8))
}

private func fail(_ code: String, _ message: String, exitCode: Int32 = 2) -> Never {
    emitJSON(
        [
            "contract_version": contractVersion,
            "status": "ERROR",
            "error_code": code,
            "message": message,
        ],
        to: FileHandle.standardError
    )
    exit(exitCode)
}

private func dictionary(_ value: Any?) -> [CFString: Any] {
    if let typed = value as? [CFString: Any] {
        return typed
    }
    if let bridged = value as? [String: Any] {
        var result: [CFString: Any] = [:]
        for (key, item) in bridged {
            result[key as CFString] = item
        }
        return result
    }
    return [:]
}

private func text(_ value: Any?) -> String? {
    guard let value else { return nil }
    if let string = value as? String {
        let trimmed = string.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
    if let number = value as? NSNumber {
        // NSNumber.stringValue não depende da localidade do processo e evita
        // que um valor numérico válido desapareça por diferença de bridging.
        return number.stringValue
    }
    return nil
}

private func number(_ value: Any?) -> Double? {
    guard let value else { return nil }
    if let number = value as? NSNumber {
        let result = number.doubleValue
        return result.isFinite ? result : nil
    }
    if let string = value as? String {
        let normalized = string.trimmingCharacters(in: .whitespacesAndNewlines)
        if let result = Double(normalized), result.isFinite {
            return result
        }
    }
    return nil
}

private func integer(_ value: Any?) -> Int? {
    guard let result = number(value), result.rounded() == result else { return nil }
    return Int(exactly: result)
}

private func setIfPresent(_ key: String, _ value: Any?, in output: inout [String: Any]) {
    if let value {
        output[key] = value
    }
}

private func normalizedCoordinate(_ magnitude: Double?, reference: String?, negativeRef: String) -> Double? {
    guard let magnitude else { return nil }
    let absolute = abs(magnitude)
    guard let reference else { return absolute }
    return reference.uppercased() == negativeRef ? -absolute : absolute
}

private func xmpNumber(_ metadata: CGImageMetadata?, path: String) -> Double? {
    guard let metadata,
          let raw = CGImageMetadataCopyStringValueWithPath(
              metadata,
              nil,
              path as CFString
          ) as String? else {
        return nil
    }
    return number(raw)
}

guard CommandLine.arguments.count == 2 else {
    fail("ARGUMENT_COUNT", "Informe exatamente um arquivo de imagem.")
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(imageURL as CFURL, nil) else {
    fail("IMAGE_SOURCE_UNAVAILABLE", "O arquivo não pôde ser aberto pelo ImageIO.")
}
guard CGImageSourceGetCount(source) > 0 else {
    fail("IMAGE_FRAME_MISSING", "O arquivo não contém quadro de imagem decodificável.")
}
guard let decoded = CGImageSourceCreateImageAtIndex(
    source,
    0,
    [kCGImageSourceShouldCache: false] as CFDictionary
) else {
    fail("PIXEL_DECODE_FAILED", "Os pixels da imagem não puderam ser decodificados.")
}
guard decoded.width > 0, decoded.height > 0 else {
    fail("INVALID_DIMENSIONS", "A imagem decodificada possui dimensões inválidas.")
}

let properties = dictionary(
    CGImageSourceCopyPropertiesAtIndex(source, 0, nil) as? [CFString: Any]
)
let tiff = dictionary(properties[kCGImagePropertyTIFFDictionary])
let exif = dictionary(properties[kCGImagePropertyExifDictionary])
let gps = dictionary(properties[kCGImagePropertyGPSDictionary])

var camera: [String: Any] = [:]
setIfPresent("make", text(tiff[kCGImagePropertyTIFFMake]), in: &camera)
setIfPresent("model", text(tiff[kCGImagePropertyTIFFModel]), in: &camera)
setIfPresent("software", text(tiff[kCGImagePropertyTIFFSoftware]), in: &camera)

var timestamps: [String: Any] = [:]
setIfPresent("datetime_original", text(exif[kCGImagePropertyExifDateTimeOriginal]), in: &timestamps)
setIfPresent("datetime_digitized", text(exif[kCGImagePropertyExifDateTimeDigitized]), in: &timestamps)
setIfPresent("datetime_tiff", text(tiff[kCGImagePropertyTIFFDateTime]), in: &timestamps)
setIfPresent(
    "offset_time_original",
    text(exif[kCGImagePropertyExifOffsetTimeOriginal]),
    in: &timestamps
)
setIfPresent(
    "subsec_time_original",
    text(exif[kCGImagePropertyExifSubsecTimeOriginal]),
    in: &timestamps
)

let latitudeRef = text(gps[kCGImagePropertyGPSLatitudeRef])
let longitudeRef = text(gps[kCGImagePropertyGPSLongitudeRef])
let altitudeRef = integer(gps[kCGImagePropertyGPSAltitudeRef])
let latitude = normalizedCoordinate(
    number(gps[kCGImagePropertyGPSLatitude]),
    reference: latitudeRef,
    negativeRef: "S"
)
let longitude = normalizedCoordinate(
    number(gps[kCGImagePropertyGPSLongitude]),
    reference: longitudeRef,
    negativeRef: "W"
)
let altitudeMagnitude = number(gps[kCGImagePropertyGPSAltitude])
let altitude = altitudeMagnitude.map { altitudeRef == 1 ? -abs($0) : abs($0) }

var gpsOutput: [String: Any] = [:]
setIfPresent("latitude", latitude, in: &gpsOutput)
setIfPresent("latitude_ref", latitudeRef, in: &gpsOutput)
setIfPresent("longitude", longitude, in: &gpsOutput)
setIfPresent("longitude_ref", longitudeRef, in: &gpsOutput)
setIfPresent("altitude_m", altitude, in: &gpsOutput)
setIfPresent("altitude_ref", altitudeRef, in: &gpsOutput)
setIfPresent("date_stamp", text(gps[kCGImagePropertyGPSDateStamp]), in: &gpsOutput)
setIfPresent("time_stamp", text(gps[kCGImagePropertyGPSTimeStamp]), in: &gpsOutput)
setIfPresent("image_direction_deg", number(gps[kCGImagePropertyGPSImgDirection]), in: &gpsOutput)
setIfPresent("image_direction_ref", text(gps[kCGImagePropertyGPSImgDirectionRef]), in: &gpsOutput)
setIfPresent(
    "horizontal_positioning_error_m",
    number(gps[kCGImagePropertyGPSHPositioningError]),
    in: &gpsOutput
)

var optics: [String: Any] = [:]
setIfPresent("focal_length_mm", number(exif[kCGImagePropertyExifFocalLength]), in: &optics)
setIfPresent(
    "focal_length_35mm",
    number(exif[kCGImagePropertyExifFocalLenIn35mmFilm]),
    in: &optics
)

var orientation: [String: Any] = [:]
setIfPresent("exif_orientation", integer(properties[kCGImagePropertyOrientation]), in: &orientation)

let metadata = CGImageSourceCopyMetadataAtIndex(source, 0, nil)
let djiPaths: [(String, String)] = [
    ("absolute_altitude_m", "drone-dji:AbsoluteAltitude"),
    ("relative_altitude_m", "drone-dji:RelativeAltitude"),
    ("gimbal_pitch_deg", "drone-dji:GimbalPitchDegree"),
    ("gimbal_yaw_deg", "drone-dji:GimbalYawDegree"),
    ("gimbal_roll_deg", "drone-dji:GimbalRollDegree"),
    ("flight_pitch_deg", "drone-dji:FlightPitchDegree"),
    ("flight_yaw_deg", "drone-dji:FlightYawDegree"),
    ("flight_roll_deg", "drone-dji:FlightRollDegree"),
    ("gps_latitude", "drone-dji:GPSLatitude"),
    ("gps_longitude", "drone-dji:GPSLongitude"),
]
var djiXMP: [String: Any] = [:]
for (outputKey, path) in djiPaths {
    setIfPresent(outputKey, xmpNumber(metadata, path: path), in: &djiXMP)
}

var whitelisted: [String: Any] = [
    "pixel_width": decoded.width,
    "pixel_height": decoded.height,
]
if !camera.isEmpty { whitelisted["camera"] = camera }
if !timestamps.isEmpty { whitelisted["timestamps"] = timestamps }
if !gpsOutput.isEmpty { whitelisted["gps"] = gpsOutput }
if !orientation.isEmpty { whitelisted["orientation"] = orientation }
if !optics.isEmpty { whitelisted["optics"] = optics }
if !djiXMP.isEmpty { whitelisted["dji_xmp"] = djiXMP }

emitJSON(
    [
        "contract_version": contractVersion,
        "status": "OK",
        "decode_status": "PIXELS_DECODED_AND_DIMENSIONS_VALIDATED",
        "metadata": whitelisted,
    ],
    to: FileHandle.standardOutput
)
