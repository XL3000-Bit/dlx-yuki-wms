package com.dlxyuki.wms.document;

import com.dlxyuki.wms.config.ApiException;
import com.dlxyuki.wms.pickingbol.PickingBolService;
import com.dlxyuki.wms.user.UserAccount;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/documents")
public class OperationalDocumentDownloadController {
    private final OperationalDocumentRepository repository;
    private final PickingBolService pickingBolService;
    private final Path storageRoot;

    public OperationalDocumentDownloadController(OperationalDocumentRepository repository,
                                                  PickingBolService pickingBolService,
                                                  @Value("${DOCUMENT_STORAGE_ROOT:data/documents}") String storageRoot) {
        this.repository=repository;this.pickingBolService=pickingBolService;this.storageRoot=Path.of(storageRoot).toAbsolutePath().normalize();
    }

    @GetMapping("/{document_id}/download")
    ResponseEntity<byte[]> download(@PathVariable("document_id") long id,@AuthenticationPrincipal UserAccount user) {
        DocumentDownload document=repository.findDownload(id,user).orElseThrow(()->new ApiException(HttpStatus.NOT_FOUND,"Document not found"));
        String filename=safeFilename(document.originalFilename());
        byte[] content;
        String contentType=document.contentType();
        if(document.generated()&&document.bolId()!=null){content=pickingBolService.exportBolPdf(document.bolId(),user);contentType=MediaType.APPLICATION_PDF_VALUE;}
        else{content=storedContent(document.storageKey());}
        MediaType mediaType;
        try{mediaType=contentType==null?MediaType.APPLICATION_OCTET_STREAM:MediaType.parseMediaType(contentType);}catch(IllegalArgumentException e){mediaType=MediaType.APPLICATION_OCTET_STREAM;}
        return ResponseEntity.ok().contentType(mediaType).header(HttpHeaders.CONTENT_DISPOSITION,"attachment; filename=\""+filename+"\"").body(content);
    }

    private byte[] storedContent(String storageKey) {
        if(storageKey==null||storageKey.isBlank())throw contentNotFound();
        Path file=storageRoot.resolve(storageKey).normalize();
        if(!file.startsWith(storageRoot)||!Files.isRegularFile(file))throw contentNotFound();
        try{return Files.readAllBytes(file);}catch(IOException e){throw contentNotFound();}
    }
    private static String safeFilename(String name){if(name==null||name.isBlank())return "document";return Path.of(name).getFileName().toString().replace("\"","");}
    private static ApiException contentNotFound(){return new ApiException(HttpStatus.NOT_FOUND,"Document content not found");}
}
